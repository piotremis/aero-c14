"""Schedule C14 access windows, reads and control operations."""
from dataclasses import dataclass
from .decode import decode
from .protocol import AIR_QUALITY_FRAME_KEY, is_gateway_frame
from .queries import build_read_query
from .commands import BypassOperation, BoostOperation, VentilationOperation, CommandError, VENTILATION_VALUES
from .commands import ParameterOperation, DirectParameterOperation, PowerOperation, HolidayOperation, BypassModeOperation, ParameterRefreshOperation, FilterResetOperation, LedFlagOperation
from .parameters import PARAMETERS, CARD_PARAMETER_KEYS, additional_batches
from .clock import ClockSyncOperation, build_clock_query, parse_clock_reply
from .direct import boost_broadcast, ventilation_broadcast, aero_control_poll, bypass_control, gwc_control, fireplace_control, power_broadcast, holiday_broadcast, context_matches_template

WINDOW_OPEN = bytes.fromhex('e4 45 34 70 78 ' + '30 '*24 + '23')
WINDOW_CLOSE = bytes.fromhex('e4 45 3c 70 00 ' + '30 '*24 + '23')
WINDOW_ACK = bytes.fromhex('f0 65 21 29 ' + '00 '*25 + '23')
GATEWAY_POLL = bytes.fromhex('f0 44 4e 29 ' + '7e '*25 + '23')
NANO_STATUS_POLL = bytes.fromhex('a9 44 30 70 ' + '30 '*25 + '23')
AERO_STATUS_POLL = bytes.fromhex('e3 44 6a 70 ' + '30 '*25 + '23')

READ_BATCHES = ((0x0125,0x0040,0x0127,0x004D,0x004E,0x004F),
                (0x0050,0x0051,0x0052,0x0053,0x0054,0x0055))


ACCESS_TRIGGERS = frozenset(('E4/21/29','E5/21/29','E4/21/63','E5/21/63',
    'DE/44/29','DE/56/29','8B/44/29','8C/44/29','AA/44/29','D0/44/29','96/44/29'))


RELEASE_RESUME_KEYS = frozenset(('E3/56/29','E2/44/29','F0/44/29','81/44/29',
    'DE/44/29','DE/56/29','8B/44/29','8C/44/29','AA/44/29','D0/44/29','96/44/29'))


@dataclass(frozen=True)
class Transmission:
    purpose: str
    packet: bytes


class LocalPolling:
    RESPONSE_NS = 2_000_000_000
    MAX_READS_PER_WINDOW = 18  
    MAX_PARAMETER_READS_PER_WINDOW = 17

    def __init__(self, enabled=False, *, gateway_detection=True, extended_parameters=False, solicit_status=False, direct_boost=False, direct_ventilation=False, direct_user_controls=False):
        if type(enabled) is not bool:
            raise ValueError('Local polling must be boolean')
        if type(extended_parameters) is not bool:
            raise ValueError('Extended parameters must be boolean')
        if type(gateway_detection) is not bool:
            raise ValueError('Gateway detection must be boolean')
        self.gateway_detection = gateway_detection
        self.extended_parameters = extended_parameters
        if type(solicit_status) is not bool:
            raise ValueError('Status solicitation must be boolean')
        self.solicit_status = solicit_status
        if type(direct_boost) is not bool:
            raise ValueError('Direct boost must be boolean')
        self.direct_boost = direct_boost
        if type(direct_ventilation) is not bool:
            raise ValueError("Direct ventilation must be boolean")
        self.direct_ventilation = direct_ventilation
        if type(direct_user_controls) is not bool:raise ValueError("Direct user controls must be boolean")
        self.direct_user_controls = direct_user_controls
        self.read_batches = READ_BATCHES + (additional_batches(READ_BATCHES)
                                            if extended_parameters else ())
        self.unique_batch_indices = tuple(dict.fromkeys(
            self.read_batches.index(batch) for batch in self.read_batches))
        card_addresses = {PARAMETERS[key].address for key in CARD_PARAMETER_KEYS}
        schedule_addresses = {p.address for p in PARAMETERS.values() if p.category == 'schedule'}
        self.card_batches = tuple(i for i in self.unique_batch_indices
            if i < len(READ_BATCHES) or card_addresses.intersection(self.read_batches[i]))
        self.schedule_batches = tuple(i for i in self.unique_batch_indices
            if schedule_addresses.intersection(self.read_batches[i]))
        self.background_batches = tuple(i for i in self.unique_batch_indices
            if i not in self.card_batches + self.schedule_batches)
        self.enabled = enabled
        self.blocked = self.fault = False
        self.failures = self.successes = self.consecutive_failures = 0
        self.successful_read_windows = 0
        self.telemetry_reads = 0
        self.telemetry_timeouts = 0
        self.sent_packets = self.sent_bytes = 0
        self.last_error = None
        self.last_success_ns = None
        self.command = None
        self.autonomous_supported = True
        self.autonomous_windows = self.autonomous_successes = 0
        self.autonomous_recoveries = 0
        self.autonomous_disabled_reason = None
        self.last_failure = None
        self.resumed_releases = 0
        self.last_release_status = None
        self.reset_connection()

    def reset_connection(self):
        if self.command is not None:
            self.command.fail('connection_reset')
        self.phase = 'disconnected'
        self.polls = self.batch = 0
        
        
        self._initial_remaining = list(self.unique_batch_indices)
        self._initial_batch_count = len(self._initial_remaining)
        self._intent = self._last_packet = None
        self.deadline = None
        self._closing_error = None
        self._window_kind = 'read'
        self._window_batch = None
        self._window_remaining = []
        self._window_completed = []
        self._window_background_completed = []
        self._window_queries = 0
        self._background_cursor = 0
        self._schedule_cursor = 0
        self._read_candidate = None
        self._read_sent_ns = None
        self._read_owner = None
        self._telemetry_disabled = False
        self._reading_telemetry = False
        self._window_telemetry_completed = False
        self._access_confirmed = False
        self._access_opportunity = None
        self._aero_generation = 0
        self._last_regular_read_generation = -1
        self._autonomous_read_since_poll = False
        self._window_autonomous = False
        self._window_regular = False
        self._window_aero_generation = 0
        self._autonomous_recovery_reads = 0
        self._nano_template = self._config_template = None
        self._config_templates = {}
        self._direct_due = self._direct_write_due = None
        self._direct_polls = 0
        self._direct_config = None
        self._direct_packet = None
        self._direct_response_pending = False
        self._release_guard_until = 0
        self._drain_packet = None

    def request_bypass(self, enabled, now, *, stale_ns):
        return self._request(BypassOperation,enabled,now,stale_ns)

    def request_boost(self, enabled, now, *, stale_ns):
        return self._request(BoostOperation,enabled,now,stale_ns)

    def request_clock_sync(self, provider, now, *, stale_ns):
        if not callable(provider):
            raise ValueError('Clock source must be callable')
        self._check_request()
        self.command = ClockSyncOperation(provider, now, stale_ns)
        return self.command

    def request_bypass_mode(self, value, now, *, stale_ns):
        if not self.extended_parameters:
            raise CommandError('control_unavailable')
        if not isinstance(value, str) or value not in ('OFF', 'AUTO', 'ON'):
            raise ValueError('Unsupported bypass mode')
        self._check_request()
        self.command = BypassModeOperation(value, now, stale_ns)
        return self.command

    def request_ventilation(self, selection, now, *, stale_ns):
        if not isinstance(selection,str) or selection not in VENTILATION_VALUES:
            raise ValueError('Unsupported ventilation selection')
        if selection in ('stopped', 'holiday_schedule') and not self.extended_parameters:
            raise CommandError('control_unavailable')
        return self._request(VentilationOperation,selection,now,stale_ns)

    def request_parameter(self, key, value, now, *, stale_ns):
        if not self.extended_parameters or key not in PARAMETERS or key in ('bypass', 'boost', 'ventilation_work_mode'):
            raise CommandError('control_unavailable')
        parameter = PARAMETERS[key]
        parameter.encode(value)  
        self._check_request()
        batch = next(i for i, addresses in enumerate(self.read_batches) if parameter.address in addresses)
        operation = HolidayOperation if key == "holiday_mode" else PowerOperation if key == "ventilation_enabled" else DirectParameterOperation if key in ("gwc_mode", "fireplace_active") else ParameterOperation
        self.command = operation(parameter, value, now, stale_ns, batch)
        return self.command

    def request_led_flag(self, key, bit, enabled, now, *, stale_ns):
        if not self.extended_parameters or key not in PARAMETERS:
            raise CommandError('control_unavailable')
        parameter = PARAMETERS[key]
        batch = next(i for i, addresses in enumerate(self.read_batches) if parameter.address in addresses)
        operation = LedFlagOperation(parameter, bit, enabled, now, stale_ns, batch)
        self._check_request()
        self.command = operation
        return operation

    def request_parameter_refresh(self, key, now, *, stale_ns):
        if not self.extended_parameters or key not in PARAMETERS:
            raise CommandError('control_unavailable')
        self._check_request(for_write=False)
        parameter = PARAMETERS[key]
        batch = next(i for i, addresses in enumerate(self.read_batches) if parameter.address in addresses)
        self.command = ParameterRefreshOperation(parameter, now, stale_ns, batch)
        return self.command

    def request_filter_reset(self, now, *, stale_ns):
        if not self.extended_parameters:
            raise CommandError('control_unavailable')
        self._check_request()
        batch = next(i for i, addresses in enumerate(self.read_batches) if 0x0055 in addresses)
        self.command = FilterResetOperation(now, stale_ns, batch)
        return self.command

    def _request(self, operation_type, enabled, now, stale_ns):
        if operation_type is not VentilationOperation and type(enabled) is not bool:
            raise ValueError('Bypass requires a boolean')
        self._check_request()
        self.command = operation_type(enabled, now, stale_ns)
        return self.command

    def _check_request(self, *, for_write=True):
        if self.command is not None and self.command.pending:
            if for_write and isinstance(self.command, ParameterRefreshOperation):
                self.command.fail('superseded_by_write')
            else:
                raise CommandError('busy')
        if self.phase == 'draining' or self.phase != 'baseline' and self._window_kind in ('write', 'clock'):
            raise CommandError('busy')
        if (not self.enabled or self.blocked or self.fault or self.phase == 'disconnected'
                or (self.polls < 3 and not self._access_confirmed)):
            raise CommandError('control_unavailable')

    def cancel_command(self):
        if self.command is not None:
            self.command.fail('cancelled')

    def command_tick(self, now):
        if self.command is not None:
            self.command.tick(now, can_complete=self.phase == 'baseline')

    def transmission_valid(self, intent):
        if intent is not self._intent:
            return False
        if intent.purpose in ('write', 'clock_set', 'direct_first') and (self.command is None or not self.command.pending):
            self._failure('command_cancelled_before_write')
            return False
        return True

    def is_forwarded_echo(self, raw):
        return (self._direct_packet is not None and raw == self._direct_packet
                and self.phase not in ('baseline','disconnected'))

    def connected(self):
        self.reset_connection()
        self.phase = 'baseline'

    def disconnected(self):
        if self.phase.startswith('send_'):
            self.transport_failed()
        elif self.phase in ('opening','reading','writing','refreshing','refreshing_aero','direct_gap','direct_write_gap','closing'):
            self._failure('connection_closed_during_window')
        self.reset_connection()

    def snapshot(self):
        status = ('disabled' if not self.enabled else 'blocked' if self.blocked else
                  'fault' if self.fault else 'stopped' if self.phase=='disconnected' else
                  'learning' if self.phase=='baseline' and self.polls<3 and not self._access_confirmed else
                  'ready' if self.phase=='baseline' else 'polling')
        return {'enabled':self.enabled,'status':status,'phase':self.phase,
                'gateway_detection':self.gateway_detection,
                'extended_parameters':self.extended_parameters,'batch_count':len(self.read_batches),
                'unique_batch_count':len(self.unique_batch_indices),
                'card_batch_count':len(self.card_batches),
                'schedule_batch_count':len(self.schedule_batches),
                'background_batch_count':len(self.background_batches),
                'autonomous_access_enabled':self.autonomous_supported,
                'autonomous_windows':self.autonomous_windows,
                'successful_autonomous_windows':self.autonomous_successes,
                'autonomous_disabled_reason':self.autonomous_disabled_reason,
                'autonomous_recovery_reads':self._autonomous_recovery_reads,
                'autonomous_recoveries':self.autonomous_recoveries,
                'last_failure':dict(self.last_failure) if self.last_failure else None,
                'master_resumed_releases':self.resumed_releases,
                'last_release_status':self.last_release_status,
                'max_reads_per_window':self.MAX_READS_PER_WINDOW if self.extended_parameters else 1,
                'max_parameter_reads_per_window':self.MAX_READS_PER_WINDOW if self.extended_parameters else 1,
                'steady_parameter_reads_per_window':self.MAX_PARAMETER_READS_PER_WINDOW if self.extended_parameters else 1,
                'successful_read_windows':self.successful_read_windows,
                'humidity_telemetry_reads':self.telemetry_reads,
                'humidity_telemetry_timeouts':self.telemetry_timeouts,
                'humidity_telemetry_enabled':self.extended_parameters and not self._telemetry_disabled,
                'scan_mode':'initial' if self._initial_remaining else 'steady',
                'initial_batch_count':self._initial_batch_count,
                'initial_batches_remaining':len(self._initial_remaining),
                'baseline_polls':self.polls,'batch_index':self.batch,
                'successful_reads':self.successes,'failed_windows':self.failures,
                'consecutive_failures':self.consecutive_failures,
                'sent_packets':self.sent_packets,'sent_bytes':self.sent_bytes,
                'last_success_ns':self.last_success_ns,'last_error':self.last_error}

    def _failure(self, reason):
        self.last_failure = {'reason':reason,'phase':self.phase,
                             'autonomous':self._window_autonomous,'sent_packets':self.sent_packets}
        self._autonomous_recovery_reads = 0
        if self._window_autonomous:
            self.autonomous_supported = False
            self.autonomous_disabled_reason = reason
        self._access_opportunity = None
        if self.command is not None:
            self.command.fail(reason)
        self.failures += 1
        self.consecutive_failures += 1
        self.last_error = reason
        self.fault |= self.consecutive_failures >= 3
        self.phase = 'baseline'
        self.polls = 0
        self._intent = self._last_packet = None
        self.deadline = None
        self._closing_error = None
        self._read_candidate = None
        self._window_remaining = []
        self._window_completed = []
        self._reading_telemetry = False
        self._window_telemetry_completed = False

    def _conflict(self):
        if not self.gateway_detection:
            return
        self.blocked = True  
        self._failure('other_gateway_detected')

    def _prepare(self, purpose, packet):
        self.phase = 'send_' + purpose
        if purpose == 'read':
            self._reading_telemetry = packet[1] == 0x54
            self._read_owner = (self.command if not self._reading_telemetry
                and isinstance(self.command, ParameterRefreshOperation) and self.command.pending else None)
        self._intent = Transmission(purpose, packet)
        return self._intent

    def sent(self, intent, now):
        if intent is not self._intent:
            raise RuntimeError('Stale polling transmission')
        self.sent_packets += 1
        self.sent_bytes += len(intent.packet)
        self._last_packet = intent.packet
        self._intent = None
        self.phase = {'open':'opening','read':'reading','write':'writing','status':'refreshing','close':'closing',
                      'aero_status':'refreshing_aero',
                      'direct_first':'direct_write_gap','direct_poll':'refreshing_aero',
                      'clock_read':'clock_reading', 'clock_set':'clock_setting', 'clock_verify':'clock_verifying'}[intent.purpose]
        if intent.purpose in ('write','clock_set'):
            self.command.sent(now)
        elif intent.purpose == 'direct_first':
            self.command.direct_forwarded = True
            self._direct_packet = intent.packet
            self._direct_due = now + 750_000_000
            self._direct_write_due = now + 60_000_000
            self._direct_response_pending = intent.packet[:2] == bytes((0xE3,0x44))
        elif intent.purpose == "direct_poll":
            self._direct_polls += 1
        elif intent.purpose == 'open' and self._window_autonomous:
            self.autonomous_windows += 1
        elif intent.purpose == 'read':
            self._window_queries += 1
            if not self._reading_telemetry:
                self._read_sent_ns = now
            if (isinstance(self.command, ParameterRefreshOperation) and self.command is self._read_owner and self.command.pending
                    and self._window_kind == 'read'
                    and self.command.sent_ns is None and self._window_batch == self.command.confirmation_batch):
                self.command.sent(now)
        self.deadline = now + self.RESPONSE_NS

    def stream_gap(self, reason='stream_gap', now=None):
        if self.phase == 'draining':
            
            
            return
        if (reason == 'partial_frame_timeout' and now is not None
                and self.phase in ('reading', 'writing', 'refreshing', 'refreshing_aero',
                                   'direct_gap', 'direct_write_gap', 'clock_reading', 'clock_setting', 'clock_verifying')):
            self._drain_owned_timeout(reason, now)
            return
        self._access_opportunity = None
        if self.command is not None:
            self.command.fail(reason)
        if self.phase not in ('baseline','disconnected'):
            self._failure(reason)
        else:
            self.polls = 0

    def transport_failed(self):
        self._failure('write_failed_delivery_uncertain')
        self.fault = True  

    def _read_plan(self):
        if self.command is not None and self.command.pending:
            return [self.command.confirmation_batch]
        if not self.extended_parameters:
            return [self.batch]
        if self._initial_remaining:
            
            
            return self._initial_remaining[:self.MAX_READS_PER_WINDOW]
        
        
        schedule_count = min(4, len(self.schedule_batches))
        schedule = tuple(self.schedule_batches[(self._schedule_cursor+i) % len(self.schedule_batches)]
                         for i in range(schedule_count))
        priority = self.card_batches + schedule
        count = min(len(self.background_batches), self.MAX_PARAMETER_READS_PER_WINDOW-len(priority))
        background = [self.background_batches[(self._background_cursor+i) % len(self.background_batches)]
                      for i in range(count)]
        return list(priority) + background

    def _finish_read_window(self):
        if (self.solicit_status and self._window_kind == 'read'
                and not (self.command is not None and self.command.pending)):
            
            return self._prepare('aero_status', AERO_STATUS_POLL)
        return self._prepare('close', WINDOW_CLOSE)

    def _drain_owned_timeout(self, reason, now):
        if self.command is not None:
            self.command.fail(reason, now)
        self._closing_error = reason
        self._drain_packet = self._last_packet
        self._intent = None
        self._access_opportunity = None
        self.phase = 'draining'
        self.deadline = now + self.RESPONSE_NS

    def _is_late_owned_reply(self, frame):
        packet = self._drain_packet
        if packet is None or packet[1] not in (0x52, 0x54, 0x57):
            return False
        if frame.key != f'F0/{packet[1]+0x20:02X}/29':
            return False
        records = decode(frame).get('parameter_records', [])
        expected = [packet[i:i+2].hex().upper() for i in range(5,29,4)
                    if packet[i:i+2] != b'\x00\x00']
        return [r['address_hex'] for r in records] == expected

    def _direct_first(self, now):
        command = self.command
        if self.direct_user_controls and command.key in ('bypass', 'gwc_mode', 'fireplace_active'):
            subtype = 0x3A if command.key == 'bypass' else 0x39
            template = self._config_templates.get(subtype)
            if (not command.pending or command.sent_ns is not None or template is None
                    or not 0 <= now-template[1] <= 30_000_000_000):return None
            mode = (command.enabled if isinstance(command.enabled,str) else 'ON' if command.enabled else 'OFF')
            try:
                packet = (bypass_control(template[0], mode) if command.key == 'bypass'
                          else fireplace_control(template[0], command.enabled) if command.key=='fireplace_active'
                          else gwc_control(template[0], mode))
            except ValueError:return None
            self._direct_config = packet
            return self._prepare('direct_first', packet)
        supported = ((self.direct_user_controls and isinstance(command, PowerOperation))
            or (self.direct_boost and isinstance(command, BoostOperation))
            or (self.direct_ventilation and isinstance(command, VentilationOperation)
                and command.enabled in ('stopped', 'B1', 'B2', 'B3')))
        if (not supported or not command.pending or command.sent_ns is not None
                or self._nano_template is None or self._config_template is None
                or any(not 0 <= now-t[1] <= 30_000_000_000
                       for t in (self._nano_template, self._config_template))):
            return None
        if (getattr(command,'stored_only',False) or not context_matches_template(
                self._nano_template[0],getattr(command,'runtime_context',None),command.key,now)):
            return None
        try:
            packet = (holiday_broadcast(self._nano_template[0], command.enabled, command.resume_level)
                if isinstance(command, HolidayOperation) else power_broadcast(self._nano_template[0], command.enabled, command.resume_level)
                if isinstance(command, PowerOperation) else boost_broadcast(self._nano_template[0], command.enabled)
                if isinstance(command, BoostOperation) else
                ventilation_broadcast(self._nano_template[0], command.enabled))
            self._direct_config = aero_control_poll(self._config_template[0])
        except ValueError:
            return None
        return self._prepare('direct_first', packet)

    def _direct_report_matches(self, values):
        if isinstance(self.command, PowerOperation):
            return values.get('ventilation_reported_level') == self.command.reported_level
        if self.command.key == 'bypass':
            target = self.command.enabled
            if target == 'AUTO':return 'bypass_reported_open' in values
            return values.get('bypass_reported_open') is (target is True or target == 'ON')
        if self.command.key == 'fireplace_active':
            return values.get('fan_a_percent') is not None and values.get('fan_b_percent') is not None
        if self.command.key == 'gwc_mode':
            return 'gwc_reported_active' in values and (self.command.enabled == 'auto' or values['gwc_reported_active'] is False)
        if isinstance(self.command, BoostOperation):
            return values.get('boost_active') is self.command.enabled
        return (values.get('ventilation_reported_level') == self.command.enabled
                and values.get('boost_active') is False)

    def _start_queued_write(self, now):
        """Use the owned window after a complete reply; never interrupt bytes."""
        command = self.command
        if (self._window_kind != 'read' or command is None or not command.pending
                or isinstance(command, (ParameterRefreshOperation, ClockSyncOperation)) or command.sent_ns is not None):
            return None
        needed = 3 if isinstance(command, LedFlagOperation) else 2
        if ((self.solicit_status and command.key == 'boost')
                or (self.direct_ventilation and isinstance(command, VentilationOperation))
                or (self.direct_user_controls and command.key in ('bypass', 'gwc_mode', 'fireplace_active', 'ventilation_enabled', 'holiday_mode'))):
            needed += 5
        if self._window_queries + needed > self.MAX_READS_PER_WINDOW:
            return None
        self._window_background_completed = list(self._window_completed)
        self._window_completed = []
        self._window_remaining = []
        self._window_kind = 'write'
        self._read_candidate = self._read_sent_ns = self._read_owner = None
        if isinstance(command, LedFlagOperation):
            self._window_batch = command.confirmation_batch
            return self._prepare('read', build_read_query(list(self.read_batches[self._window_batch])))
        return self._direct_first(now) or self._prepare('write', command.packet())

    def _commit_scan_progress(self, completed_indices):
        completed = {self.read_batches[i] for i in completed_indices}
        self._initial_remaining = [i for i in self._initial_remaining
                                   if self.read_batches[i] not in completed]
        background = [i for i in completed_indices if i in self.background_batches]
        if background:
            self._background_cursor = (self.background_batches.index(background[-1])+1) % len(self.background_batches)
        schedule = [i for i in completed_indices if i in self.schedule_batches]
        if schedule:
            self._schedule_cursor = (self.schedule_batches.index(schedule[-1])+1) % len(self.schedule_batches)

    def _open_window(self, *, autonomous=False):
        self._direct_packet = self._direct_config = None
        self._direct_response_pending = False
        self._direct_polls = 0
        refreshing = isinstance(self.command, ParameterRefreshOperation) and self.command.pending
        self._window_kind = ('write' if self.command is not None and not refreshing
            and self.command.pending and self.command.sent_ns is None else 'read')
        if self._window_kind == 'write' and isinstance(self.command, ClockSyncOperation):
            self._window_kind = 'clock'
        plan = self._read_plan() if self._window_kind == 'read' else []
        self._window_batch = plan[0] if plan else self.batch
        self._window_remaining = plan[1:]
        self._window_completed = []
        self._window_background_completed = []
        self._window_queries = 0
        self._window_telemetry_completed = self._reading_telemetry = False
        self._closing_error = self._read_candidate = None
        self._window_autonomous = autonomous
        self._window_regular = self.command is None or not self.command.pending
        self._window_aero_generation = self._aero_generation
        self._access_opportunity = None
        return self._prepare('open', WINDOW_OPEN)

    def _autonomous_open(self, now, quiet_ns):
        if (not self.enabled or not self.autonomous_supported or self.blocked or self.fault
                or self.phase != 'baseline' or self._access_opportunity is None
                or now < self._release_guard_until
                or quiet_ns is None or quiet_ns < 60_000_000
                or not 60_000_000 <= now-self._access_opportunity <= 350_000_000):
            return None
        if self.command is not None and self.command.pending:
            if self.command.sent_ns is not None:
                return None  
        elif not self._initial_remaining and self._aero_generation <= self._last_regular_read_generation:
            return None  
        return self._open_window(autonomous=True)

    def batch_received(self, frames, now, *, clean=True, partial=False):
        if not self.enabled or self.blocked or self.fault:
            return None
        if not clean:
            owned_reply = self.phase in ('reading','writing','refreshing','refreshing_aero',
                'direct_gap','direct_write_gap','closing','draining','clock_reading','clock_setting','clock_verifying')
            self.stream_gap('corrupt_stream')
            if owned_reply:


                if self.gateway_detection and any(decode(frame)['valid'] and
                       is_gateway_frame(frame)
                       for frame in frames):
                    self._conflict()
                return None
        if self.command is not None:
            self.command.tick(now)
        intent = None
        for index, frame in enumerate(frames):
            if not decode(frame)['valid']:
                self.stream_gap('corrupt_frame')
                intent = None
                continue
            
            if self.is_forwarded_echo(frame.raw) or (self.phase not in ('baseline','disconnected') and frame.raw == self._last_packet):
                continue
            key = frame.key
            if key == 'E4/21/29':
                self._nano_template = (frame.raw, now)
            elif key == 'E3/44/29' and frame.raw[4] in (0x39,0x3A,0x3B):
                self._config_template = (frame.raw, now)
                self._config_templates[frame.raw[4]] = (frame.raw, now)
            foreign = is_gateway_frame(frame)
            if foreign:
                if self.gateway_detection:
                    self._conflict()
                    return None
                continue
            if self.command is not None:
                self.command.observe(decode(frame)['values'], now)
            if key == AIR_QUALITY_FRAME_KEY:
                
                
                continue
            if self.phase == 'draining':
                if key in RELEASE_RESUME_KEYS:
                    self._failure(self._closing_error)
                elif self.gateway_detection and key in ('F0/72/29','F0/74/29','F0/77/29') and not self._is_late_owned_reply(frame):
                    self._conflict()
                
                
                continue
            if self.phase == 'baseline':
                if key == 'F0/65/29' and frame.raw[4] == 0 and now < self._release_guard_until:
                    
                    
                    self._release_guard_until = 0
                    continue
                self._access_opportunity = (now if key in ACCESS_TRIGGERS and clean
                    and not partial and index == len(frames)-1 else None)
                if key == 'E4/21/63':
                    self._aero_generation += 1
                if self.gateway_detection and key in ('F0/65/29','F0/72/29','F0/74/29','F0/77/29'):
                    self._conflict()
                    return None
                if frame.raw == GATEWAY_POLL:
                    self.polls += 1
                    pending = self.command is not None and self.command.pending
                    already_read = self._autonomous_read_since_poll and not pending and not self._initial_remaining
                    self._autonomous_read_since_poll = False
                    if already_read:
                        continue
                    if self.polls >= 3 and clean and not partial and index==len(frames)-1 and now >= self._release_guard_until:
                        intent = self._open_window()
            elif self.phase in ('opening','reading','writing','refreshing','refreshing_aero','direct_gap','direct_write_gap','closing',
                                'clock_reading','clock_setting','clock_verifying'):
                if now > self.deadline:
                    if self.phase not in ('opening', 'closing'):
                        self._drain_owned_timeout('late_response', now)
                    else:
                        self._failure('late_response')
                    intent = None
                    continue
                if key == 'F0/65/29' and self.phase in ('opening', 'closing') and frame.raw[4] != 0:
                    self._failure('access_denied' if frame.raw[4] == 1 else 'invalid_access_status')
                    intent = None
                    continue
                
                
                if self.phase == 'opening' and key == 'F0/65/29' and frame.raw[4] == 0:
                    if self._window_kind == 'clock':
                        intent = self._prepare('clock_read', build_clock_query())
                    elif self._window_kind == 'write':
                        if self.command.pending:
                            if isinstance(self.command, LedFlagOperation):
                                self._window_batch = self.command.confirmation_batch
                                intent = self._prepare('read', build_read_query(list(self.read_batches[self._window_batch])))
                            else:
                                intent = self._direct_first(now) or self._prepare('write', self.command.packet())
                        else:
                            intent = self._prepare('close', WINDOW_CLOSE)
                    else:
                        intent = (self._start_queued_write(now) or
                                  self._prepare('read',build_read_query(list(self.read_batches[self._window_batch]))))
                elif self.phase in ('clock_reading','clock_setting','clock_verifying') and key == 'F0/7A/29':
                    try:
                        value = parse_clock_reply(frame.raw)
                        if self.phase == 'clock_reading' and self.command.pending:
                            intent = self._prepare('clock_set', self.command.packet())
                        elif self.phase == 'clock_setting' and self.command.pending:
                            if abs((value-self.command.target).total_seconds()) > 60:
                                raise ValueError('Clock echo mismatch')
                            self.command.echoed = True
                            intent = self._prepare('clock_verify', build_clock_query())
                        else:
                            expected = self.command.enabled().replace(tzinfo=None,second=0,microsecond=0)
                            if abs((value-expected).total_seconds()) > 60:
                                raise ValueError('Clock readback mismatch')
                            self.command.confirmations['verified'] = True
                            self.command.confirmations['clock_local_time'] = value.isoformat()
                            intent = self._prepare('close', WINDOW_CLOSE)
                    except ValueError:
                        self._closing_error = 'invalid_clock_reply'
                        self.command.fail(self._closing_error, now)
                        intent = self._prepare('close', WINDOW_CLOSE)
                elif self.phase == 'direct_write_gap' and key == 'E4/21/63':
                    
                    
                    self._direct_response_pending = False
                    self._direct_write_due = max(self._direct_write_due, now + 60_000_000)
                    continue
                elif self.phase == 'refreshing' and key == 'E4/21/29':
                    intent = self._prepare('aero_status', AERO_STATUS_POLL)
                elif self.phase == 'refreshing_aero' and key == 'E4/21/63':
                    if (getattr(self.command, 'direct_forwarded', False)
                            and not self._direct_report_matches(decode(frame)['values'])
                            and self._direct_polls < 3 and self.command.pending):
                        self.phase = 'direct_gap'
                        self._direct_due = now + 750_000_000
                    else:
                        intent = self._prepare('close', WINDOW_CLOSE)
                elif (self.phase == 'reading' and self._reading_telemetry
                        and key == 'F0/74/29' and frame.raw[4] == 0):
                    addresses = [r['address_hex'] for r in decode(frame)['parameter_records']]
                    if addresses == ['0010']:
                        self._window_telemetry_completed = True
                        intent = self._start_queued_write(now) or self._finish_read_window()
                    else:
                        self._failure('wrong_telemetry_readback')
                elif self.phase == 'writing' and key == 'F0/77/29' and frame.raw[4] == 0:
                    records = decode(frame)['parameter_records']
                    if (len(records) == 1 and records[0]['address_hex'] == self.command.address
                            and records[0]['encoded_integer'] == self.command.wire_value):
                        self.command.echoed = True
                    else:
                        self._closing_error = 'wrong_write_echo'
                        self.command.fail('wrong_write_echo', now)
                    
                    
                    if self.command.pending and self.command.echoed and not self._closing_error:
                        self._window_batch = self.command.confirmation_batch
                        intent = self._prepare('read',build_read_query(list(self.read_batches[self._window_batch])))
                    else:
                        intent = self._prepare('close', WINDOW_CLOSE)
                elif self.phase == 'reading' and not self._reading_telemetry and key == 'F0/72/29' and frame.raw[4]==0:
                    addresses=[int(r['address_hex'],16) for r in decode(frame)['parameter_records']]
                    if (addresses == list(self.read_batches[self._window_batch])
                            and self._window_kind == 'write' and isinstance(self.command, LedFlagOperation)
                            and not self.command.prepared):
                        if self.command.pending:
                            try:
                                self.command.prepare_from_read(decode(frame)['values'].get(self.command.readback_key))
                            except (ValueError, KeyError):
                                self._closing_error = 'invalid_mask_readback'
                                self.command.fail(self._closing_error, now)
                        intent = (self._prepare('write', self.command.packet()) if self.command.pending
                                  else self._prepare('close', WINDOW_CLOSE))
                    elif addresses == list(self.read_batches[self._window_batch]):
                        if self.command is not None:
                            self._read_candidate = (decode(frame)['values'].get(self.command.readback_key), now)
                        self._window_completed.append(self._window_batch)
                        
                        
                        urgent = self._start_queued_write(now)
                        if urgent is not None:
                            intent = urgent
                        elif self._window_remaining and not (self.command is not None and self.command.pending):
                            self._window_batch = self._window_remaining.pop(0)
                            intent = self._prepare('read',build_read_query(list(self.read_batches[self._window_batch])))
                        elif (self._window_kind == 'read' and self.extended_parameters and not self._telemetry_disabled
                                and len(self._window_completed) < self.MAX_READS_PER_WINDOW
                                and not (self.command is not None and self.command.pending)):
                            intent = self._prepare('read',build_read_query([0x0010],command=0x54))
                        else:
                            if (self._window_kind == 'write' and getattr(self.command, 'direct_forwarded', False)):
                                if self._read_candidate[0] == self.command.expected_values()[self.command.readback_key] and self.command.pending:
                                    self.phase = 'direct_gap'
                                else:
                                    self._closing_error = 'wrong_direct_readback'
                                    self.command.fail(self._closing_error, now)
                                    intent = self._prepare('close', WINDOW_CLOSE)
                            elif (self.solicit_status and self._window_kind == 'write'
                                    and self.command.key in ('boost','bypass','gwc_mode','fireplace_active','ventilation',
                                                            'ventilation_enabled','holiday_mode','away_mode') and self.command.pending
                                    and self.command.echoed):
                                intent = self._prepare('status', NANO_STATUS_POLL)
                            else:
                                intent=self._finish_read_window()
                    else:
                        self._failure('wrong_readback')
                elif self.phase == 'closing' and ((key == 'F0/65/29' and frame.raw[4] == 0)
                                                  or key in RELEASE_RESUME_KEYS):
                    if self._closing_error and self._closing_error != 'telemetry_timeout':
                        self._failure(self._closing_error)
                        if key == 'F0/65/29' and frame.raw[4] == 0:
                            
                            
                            self.polls = max(self.polls, 3)
                    else:
                        self.last_release_status = 'ack' if key == 'F0/65/29' else 'master_resumed'
                        self.resumed_releases += int(key != 'F0/65/29')
                        self._release_guard_until = 0 if key == 'F0/65/29' else now+2_000_000_000
                        self._access_confirmed = True
                        self.autonomous_successes += int(self._window_autonomous)


                        if (not self.autonomous_supported and not self.blocked and not self.fault
                                and not self._window_autonomous and self._window_kind == 'read'
                                and self._window_completed and self._closing_error is None):
                            self._autonomous_recovery_reads += 1
                            if self._autonomous_recovery_reads >= 3:
                                self.autonomous_supported = True
                                self.autonomous_disabled_reason = None
                                self.autonomous_recoveries += 1
                        if self._window_kind == 'clock':
                            self.command.write_closed = True
                        elif self._window_kind == 'write':
                            self.command.write_closed = True
                            if (self._read_candidate is not None and self._read_sent_ns is not None
                                    and self._read_sent_ns > self.command.sent_ns):
                                self.command.readback(*self._read_candidate)
                                self.successes += 1 + int(isinstance(self.command, LedFlagOperation))
                                self.successful_read_windows += 1
                            self.batch = self.command.confirmation_batch
                            self.successes += len(self._window_background_completed)
                            self.successes += int(self._window_telemetry_completed)
                            self.telemetry_reads += int(self._window_telemetry_completed)
                            self._commit_scan_progress(self._window_background_completed)
                        else:
                            if self._window_regular:
                                self._last_regular_read_generation = self._window_aero_generation
                                self._autonomous_read_since_poll |= self._window_autonomous
                            self.successes += len(self._window_completed) + int(self._window_telemetry_completed)
                            self.telemetry_reads += int(self._window_telemetry_completed)
                            self.successful_read_windows += 1
                            if (self.command is not None and self.command.sent_ns is not None
                                    and (self._read_sent_ns > self.command.sent_ns or (
                                        isinstance(self.command, ParameterRefreshOperation)
                                        and self._read_sent_ns == self.command.sent_ns))
                                    and self._window_batch == self.command.confirmation_batch
                                    and self._read_candidate is not None):
                                self.command.readback(*self._read_candidate)
                                if isinstance(self.command, ParameterRefreshOperation):
                                    self.command.read_closed = True
                            self._commit_scan_progress(self._window_completed)
                            last = self.read_batches.index(self.read_batches[self._window_batch])
                            self.batch = (self._initial_remaining[0] if self._initial_remaining else
                                self.unique_batch_indices[(self.unique_batch_indices.index(last)+1) % len(self.unique_batch_indices)]
                                if self.extended_parameters else (last+1) % len(self.read_batches))
                        self.consecutive_failures = 0
                        self.last_error = None
                        self.last_success_ns = now
                        self.phase='baseline'
                        self.deadline=None
                        self._last_packet=None
                        self._window_remaining = []
                        self._window_completed = []
                        self._window_telemetry_completed = False
                        self._reading_telemetry = False
                elif self.phase == 'closing' and key in ('E4/21/63','E5/21/63'):
                    
                    
                    continue
                else:
                    if self.gateway_detection and key in ('F0/65/29','F0/72/29','F0/74/29','F0/77/29'):
                        self._conflict()
                    else:
                        self._failure('window_interrupted')
                    intent=None
            if intent is not None and (index!=len(frames)-1 or partial or not clean):
                
                self._failure('extra_bytes_before_transmission')
                return None
        self.command_tick(now)
        return intent

    def idle(self, now, *, stream_idle, quiet_ns=None):
        self.command_tick(now)
        if self.phase == 'draining':
            if stream_idle and now <= self.deadline:
                return self._prepare('close', WINDOW_CLOSE)
            if now > self.deadline:
                self._failure('release_not_idle')
            return None
        if (self.phase == 'direct_write_gap' and not self._direct_response_pending
                and stream_idle and now >= self._direct_write_due and now <= self.deadline):
            return self._prepare('write', self.command.packet()) if self.command.pending else self._prepare('close', WINDOW_CLOSE)
        if self.phase == 'direct_gap' and self.command is not None and not self.command.pending and stream_idle:
            return self._prepare('close', WINDOW_CLOSE)
        if (self.phase == 'direct_gap' and self._direct_due is not None
                and now >= self._direct_due and now <= self.deadline and stream_idle):
            return self._prepare('direct_poll', self._direct_config)
        opening = self._autonomous_open(now, quiet_ns)
        if opening is not None:
            return opening
        if not self.enabled or self.blocked or self.fault or self.deadline is None or now <= self.deadline:
            return None
        if self.phase in ('reading', 'writing', 'refreshing', 'refreshing_aero', 'direct_gap', 'direct_write_gap', 'clock_reading', 'clock_setting', 'clock_verifying') and stream_idle:
            if self._reading_telemetry:
                
                
                self._telemetry_disabled = True
                self.telemetry_timeouts += 1
            self._closing_error=('telemetry_timeout' if self._reading_telemetry else
                'write_echo_timeout' if self.phase == 'writing' else
                'nano_status_timeout' if self.phase == 'refreshing' else
                'aero_status_timeout' if self.phase == 'refreshing_aero' else 'read_timeout')
            if self.command is not None and not self._reading_telemetry:
                self.command.fail(self._closing_error, now)
            return self._prepare('close',WINDOW_CLOSE)
        if self.phase in ('reading', 'writing', 'refreshing', 'refreshing_aero', 'direct_gap', 'direct_write_gap',
                          'clock_reading', 'clock_setting', 'clock_verifying'):
            self._drain_owned_timeout('timeout_' + self.phase, now)
        else:
            self._failure('timeout_' + self.phase)
        return None
