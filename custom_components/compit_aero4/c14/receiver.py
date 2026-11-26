"""Reconnectable receiver with optional, explicitly enabled local read polling."""
import asyncio
import math
import logging
import time
from collections.abc import Callable
from .protocol import StreamParser
from .state import Aero4State
from .polling import LocalPolling
from .commands import CommandError
from .parameters import PARAMETERS
from .control_queue import queued
from .transport import SerialConfig, TcpConfig, positive_seconds, source_for

_LOGGER = logging.getLogger(__name__)


class ReceiverCallbackError(RuntimeError):
    """Consumer errors stop the runtime, rather than trigger reconnect loops."""


class Receiver:
    
    
    PARTIAL_FRAME_NS = 500_000_000
    TCP_FAILURE_LIMIT = 5
    TCP_SLOW_RETRY_SECONDS = 300
    def __init__(self, config: SerialConfig | TcpConfig, *, stale_after: float,
                 on_update: Callable[[dict], None] | None = None,
                 retry_initial: float = 1, retry_max: float = 30,
                 factory=None, clock=time.monotonic_ns, local_polling=False, extended_parameters=False, gateway_detection=True,
                 solicit_status=False, direct_boost=False, direct_ventilation=False, direct_user_controls=False):
        positive_seconds(stale_after, 'stale_after')
        positive_seconds(retry_initial, 'retry_initial')
        positive_seconds(retry_max, 'retry_max')
        if (retry_max < retry_initial or not math.isfinite(stale_after * 1e9)
                or int(stale_after * 1e9) == 0):
            raise ValueError('Invalid retry limits or freshness threshold')
        if not isinstance(config, (SerialConfig, TcpConfig)):
            raise TypeError('Expected SerialConfig or TcpConfig')
        self.config = config
        self.state = Aero4State(stale_after_ns=int(stale_after * 1e9))
        self._callback = on_update
        self._factory = factory if factory is not None else lambda: source_for(config)
        self._clock = clock
        self._retry_initial, self._retry_max = retry_initial, retry_max
        self._sleep = asyncio.sleep
        self._connection_failures = 0
        self._retry_delay = None
        self._connection_opened_ns = None
        self._last_valid_frame_ns = None
        self._running = False
        self.polling = LocalPolling(local_polling, gateway_detection=gateway_detection, extended_parameters=extended_parameters, solicit_status=solicit_status, direct_boost=direct_boost, direct_ventilation=direct_ventilation, direct_user_controls=direct_user_controls)
        self._pending_tx = None
        self._command_changed = asyncio.Event()
        self._sequence_task = None
        self._refresh_task = None
        self.boost_timer = None
        self.control_queue = None
        self.schedule_operation = {'status': 'idle', 'completed': 0, 'error': None}
        self.observer = None
        self.status = 'stopped'
        self.last_error = None
        self._parser = StreamParser()
        self._last_rx_ns = None
        self.counters = dict(connection_attempts=0, connections=0, received_bytes=0,
            valid_frames=0, checksum_errors=0, discarded_bytes=0, truncated_bytes=0,
            observer_errors=0, stale_reconnects=0)

    def _observe(self, kind, now, **values):
        if self.observer is not None:
            try:
                self.observer({'kind':kind,'observed_ns':now,
                               'session':self.counters['connections'],**values})
            except Exception:
                self.counters['observer_errors'] += 1
                self.observer = None
                _LOGGER.exception('RX observer failed; continuing normal reception')

    def snapshot(self):
        state = self.state.snapshot(self._clock())
        problem = isinstance(self.config, TcpConfig) and self._connection_failures >= self.TCP_FAILURE_LIMIT
        connection_status = ('stopped' if self.status == 'stopped' else
            'connection_problems' if problem else
            'waiting_for_data' if self.status == 'connected' and self._last_valid_frame_ns is None else self.status)
        parameters = [info for key, info in state['fields'].items() if key.startswith('parameter_')]
        received = sum(info['observed_ns'] is not None and info['status'] != 'unavailable' for info in parameters)
        known = sum(info['status'] == 'known' for info in parameters)
        return {**state, 'polling':self.polling.snapshot(),
            'parameter_scan': {'total':len(parameters),'received':received,'known':known,'unknown_values':received-known},
            'schedule_operation': dict(self.schedule_operation),
            'control_queue': self.control_queue.snapshot() if self.control_queue is not None else {},
            'boost_timer': self.boost_timer.snapshot() if self.boost_timer is not None else {},
            'command': self.polling.command.snapshot() if self.polling.command is not None
                       else {'key':None,'status':'idle','requested':None,'error':None,'sent':False,
                             'echoed':False,'write_closed':False},
            'transport': {'kind': 'serial' if isinstance(self.config, SerialConfig) else 'tcp',
                'status': self.status, 'connected': self.status == 'connected',
                'connection_status': connection_status, 'connection_problems': problem,
                'consecutive_failures': self._connection_failures,
                'retry_delay_seconds': self._retry_delay if self.status == 'retrying' else None,
                'last_error': self.last_error, **self.counters}}

    def _publish(self):
        self._command_changed.set()
        if self._callback is not None:
            try:
                self._callback(self.snapshot())
            except Exception as error:
                raise ReceiverCallbackError('Receiver consumer failed') from error

    @queued
    async def async_set_bypass(self, enabled):
        return await self._async_set_control('bypass',enabled)

    @queued
    async def async_set_boost(self, enabled):
        if getattr(self, 'boost_timer', None) is not None and self.polling.extended_parameters:
            return await self.boost_timer.async_set_enabled(enabled)
        return await self._async_set_boost(enabled)

    async def _async_set_boost(self, enabled):
        return await self._async_set_control('boost',enabled)

    @queued
    async def async_sync_clock(self, provider):
        self._check_sequence()
        snapshot = self.snapshot()
        if not self._running or not snapshot['transport']['connected'] or not snapshot['aero_online']:
            raise CommandError('control_unavailable')
        operation = self.polling.request_clock_sync(provider, self._clock(), stale_ns=self.state.stale_after_ns)
        return await self._await_operation(operation)

    @queued
    async def async_set_ventilation(self, selection):
        return await self._async_set_control('ventilation',selection)

    @queued
    async def async_set_bypass_mode(self, mode):
        self._check_sequence()
        snapshot = self.snapshot()
        if (not self._running or not snapshot['transport']['connected'] or not snapshot['aero_online']
                or any(snapshot['fields'][key]['status'] != 'known'
                       for key in ('bypass_requested', 'bypass_reported_open'))):
            raise CommandError('control_unavailable')
        operation = self.polling.request_bypass_mode(mode, self._clock(), stale_ns=self.state.stale_after_ns)
        return await self._await_operation(operation)

    @queued
    async def async_set_parameter(self, key, value):
        if key == 'boost_duration' and getattr(self, 'boost_timer', None) is not None and self.polling.extended_parameters:
            return await self.boost_timer.async_set_duration(value)
        return await self._async_set_parameter(key, value)

    async def _async_set_parameter(self, key, value):
        self._check_sequence()
        parameter = PARAMETERS.get(key)
        snapshot = self.snapshot()
        if (parameter is None or not self._running or not snapshot['transport']['connected']
                or not snapshot['aero_online'] or snapshot['fields'][parameter.field]['status'] != 'known'):
            raise CommandError('control_unavailable')
        operation = self.polling.request_parameter(key, value, self._clock(),
                                                  stale_ns=self.state.stale_after_ns)
        self._attach_control_context(operation,snapshot)
        if (key == 'ventilation_enabled' and value is True) or (key == 'holiday_mode' and value is False):
            from .direct import resolve_manual_level
            operation.resume_level=resolve_manual_level(snapshot['fields'],leaving_holiday=key=='holiday_mode')
        return await self._await_operation(operation)

    @queued
    async def async_set_led_flag(self, key, bit, enabled):
        self._check_sequence()
        parameter = PARAMETERS.get(key)
        snapshot = self.snapshot()
        if (parameter is None or not self._running or not snapshot['transport']['connected']
                or not snapshot['aero_online'] or snapshot['fields'][parameter.field]['status'] != 'known'):
            raise CommandError('control_unavailable')
        operation = self.polling.request_led_flag(key, bit, enabled, self._clock(),
                                                  stale_ns=self.state.stale_after_ns)
        return await self._await_operation(operation)

    @queued
    async def async_reset_filter_counter(self):
        self._check_sequence()
        snapshot = self.snapshot()
        if (not self._running or not snapshot['transport']['connected'] or not snapshot['aero_online']
                or snapshot['fields']['parameter_filter_elapsed_days']['status'] != 'known'):
            raise CommandError('control_unavailable')
        operation = self.polling.request_filter_reset(self._clock(),stale_ns=self.state.stale_after_ns)
        return await self._await_operation(operation)

    def _check_sequence(self, *, write=True):
        if self._sequence_task is not None and self._sequence_task is not asyncio.current_task():
            if not write or self._sequence_task is not self._refresh_task:
                raise CommandError('busy')

    async def async_refresh_parameters(self, keys):
        """Read each required catalog batch once, without transmitting writes."""
        self._check_sequence(write=False)
        if (not isinstance(keys, (tuple, list)) or not 1 <= len(keys) <= len(PARAMETERS)
                or any(not isinstance(key, str) or key not in PARAMETERS for key in keys)):
            raise ValueError('Choose allowlisted parameter keys')
        snapshot = self.snapshot()
        if (not self._running or not snapshot['transport']['connected'] or not snapshot['aero_online']
                or not self.polling.extended_parameters):
            raise CommandError('control_unavailable')
        self.polling._check_request(for_write=False)
        
        batches = {}
        for key in keys:
            address = PARAMETERS[key].address
            batch = next(i for i, addresses in enumerate(self.polling.read_batches) if address in addresses)
            batches.setdefault(batch, key)
        self._sequence_task = asyncio.current_task()
        self._refresh_task = self._sequence_task
        try:
            for key in batches.values():
                operation = self.polling.request_parameter_refresh(key, self._clock(),
                    stale_ns=self.state.stale_after_ns)
                await self._await_operation(operation)
            return {key: self.snapshot()['fields'][PARAMETERS[key].field] for key in keys}
        finally:
            if self._sequence_task is asyncio.current_task():
                self._sequence_task = None
            if self._refresh_task is asyncio.current_task():
                self._refresh_task = None

    @queued
    async def async_set_schedule_period(self, day, period, start, end):
        from .schedule import period_keys, plan_period
        self._check_sequence()
        keys = period_keys(day, period)
        snapshot = self.snapshot()
        fields = [snapshot['fields'][PARAMETERS[key].field] for key in keys]
        if (not self.polling.extended_parameters or not self.polling.enabled
                or not self._running or not snapshot['transport']['connected'] or not snapshot['aero_online']
                or any(info['status'] != 'known' for info in fields)):
            raise CommandError('control_unavailable')
        changes = plan_period(day, period, start, end, fields[0]['value'], fields[1]['value'])
        self.polling._check_request()
        self._sequence_task = asyncio.current_task()
        self.schedule_operation = {'status': 'waiting', 'completed': 0, 'error': None,
                                   'day': day, 'period': period}
        try:
            self._publish()
            for key, value in changes:
                await self.async_set_parameter(key, value)
                self.schedule_operation['completed'] += 1
                self._publish()
            self.schedule_operation['status'] = 'succeeded'
            return dict(self.schedule_operation)
        except BaseException as error:
            self.schedule_operation.update(status='failed', error='cancelled' if isinstance(error, asyncio.CancelledError)
                                           else 'partial_or_unconfirmed')
            raise
        finally:
            self._sequence_task = None
            self._publish()

    @queued
    async def async_user_control(self, action, value):
        """Serialize card sequences; stop on an uncertain write, never replay."""
        if action not in ('mode', 'gear', 'boost'):
            raise ValueError('Unknown user action')
        allowed = {'mode': ('manual','schedule','holiday','away'),
                   'gear': ('B1','B2','B3','stopped'),
                   'boost': ('off','unlimited','15','30','60')}
        if value not in allowed[action]:
            raise ValueError('Unknown user option')
        if action == 'boost' and getattr(self, 'boost_timer', None) is not None:
            return await self.boost_timer.async_select(value)
        self._check_sequence()
        self.polling._check_request()
        fields = self.snapshot()['fields']
        needed = ['parameter_holiday_mode','parameter_away_mode'] if action in ('mode','gear') else ([] if value == 'off' else ['parameter_boost_duration','parameter_boost'])
        if any(fields[k]['status'] != 'known' for k in needed):
            raise CommandError('control_unavailable')
        
        selection = value
        if action == 'mode' and value == 'manual':
            selection = fields['ventilation_requested']['value']
            if fields['ventilation_requested']['status'] != 'known' or selection not in ('B1','B2','B3','stopped'):
                raise CommandError('control_unavailable')
        self._sequence_task = asyncio.current_task()
        try:
            if action == 'boost':
                if value == 'off':
                    return await self.async_set_boost(False)
                duration = 0 if value == 'unlimited' else int(value)
                if fields['parameter_boost_duration']['value'] != duration:
                    await self.async_set_parameter('boost_duration', duration)
                
                if fields['parameter_boost']['value'] is not True:
                    return await self.async_set_boost(True)
                return None
            
            for key, target in (('holiday_mode', action == 'mode' and value == 'holiday'),
                                ('away_mode', action == 'mode' and value == 'away')):
                if self.snapshot()['fields']['parameter_'+key]['value'] is True and not target:
                    await self.async_set_parameter(key, False)
            if action == 'gear' or value in ('manual','schedule'):
                return await self.async_set_ventilation(selection)
            return await self.async_set_parameter('holiday_mode' if value == 'holiday' else 'away_mode', True)
        finally:
            self._sequence_task = None

    def _attach_control_context(self, operation, snapshot):
        from .direct import control_context
        operation.runtime_context=control_context(snapshot['fields'])
        if operation.key=='ventilation' and operation.enabled in ('B1','B2','B3','stopped'):
            context=operation.runtime_context
            power=context.get('parameter_ventilation_enabled')
            overrides=[context.get(k) for k in ('parameter_holiday_mode','parameter_away_mode')]
            now=self._clock()
            operation.stored_only=bool((power is not None and power[0] is False and 0<=now-power[1]<=30_000_000_000)
                or any(v is not None and v[0] is True and 0<=now-v[1]<=30_000_000_000 for v in overrides))

    async def _async_set_control(self, key, enabled):
        """Wait for the existing runtime to write and confirm one operation."""
        self._check_sequence()
        snapshot = self.snapshot()
        required = {'bypass':('bypass_requested','bypass_reported_open'),
                    'boost':('boost_requested','boost_active'),
                    'ventilation':('ventilation_mode_readback','ventilation_requested')}[key]
        if (not self._running or not snapshot['transport']['connected']
                or not snapshot['aero_online'] or any(snapshot['fields'][key]['status'] != 'known'
                                                      for key in required)):
            raise CommandError('control_unavailable')
        request = {'bypass':self.polling.request_bypass,'boost':self.polling.request_boost,
                   'ventilation':self.polling.request_ventilation}[key]
        operation = request(enabled, self._clock(),
                                               stale_ns=self.state.stale_after_ns)
        self._attach_control_context(operation,snapshot)
        return await self._await_operation(operation)

    async def _await_operation(self, operation):
        try:
            self._publish()
            async with asyncio.timeout(185):
                while operation.pending:
                    self._command_changed.clear()
                    if operation.pending:
                        await self._command_changed.wait()
            if operation.status != 'succeeded':
                raise CommandError(operation.error or 'not_confirmed')
            return operation.snapshot()
        except TimeoutError as error:
            operation.fail('confirmation_timeout', self._clock())
            raise CommandError('confirmation_timeout') from error
        except asyncio.CancelledError:
            operation.fail('cancelled', self._clock())
            raise
        except Exception:
            
            
            operation.fail('caller_failed', self._clock())
            raise
        finally:
            self._publish()

    def _finish(self):
        before = self._parser.discarded_bytes
        tail = len(self._parser.buffer)
        self._parser.finish()
        self.counters['discarded_bytes'] += self._parser.discarded_bytes - before
        self.counters['truncated_bytes'] += tail

    def _feed(self, data, now):
        self._observe('rx', now, data=data)
        before = self._parser.discarded_bytes
        frames = self._parser.feed(data, now)
        self.counters['received_bytes'] += len(data)
        self.counters['discarded_bytes'] += self._parser.discarded_bytes - before
        valid = 0
        for frame in frames:
            if frame.checksum_valid:
                if not self.polling.is_forwarded_echo(frame.raw):
                    self.state.update(frame)
                valid += 1
            else:
                self.counters['checksum_errors'] += 1
        self.counters['valid_frames'] += valid
        self._pending_tx = self.polling.batch_received(frames, now,
            clean=self._parser.discarded_bytes==before and valid==len(frames),
            partial=bool(self._parser.buffer))
        return valid

    async def _transmit(self, source):
        intent, self._pending_tx = self._pending_tx, None
        self.polling.command_tick(self._clock())
        if intent is not None and self.polling.transmission_valid(intent):
            try:
                await source.write(intent.packet)
            except OSError:
                self.polling.transport_failed()
                raise
            now = self._clock()
            self.polling.sent(intent, now)
            
            self._observe('tx', now, data=intent.packet, reason=intent.purpose)

    async def run(self):
        """Run until cancelled/fatal error. Cancellation closes the active source.

        One run per instance; source operations are sequential. Retry delay grows
        after failures/EOF, resetting only after a valid frame, not a bare connect.
        """
        if self._running:
            raise RuntimeError('Receiver is already running')
        self._running = True
        delay = self._retry_initial
        try:
            while True:
                source = self._factory()
                self._parser = StreamParser()
                self._last_rx_ns = None
                self._last_valid_frame_ns = None
                self._connection_opened_ns = None
                self._retry_delay = None
                self._pending_tx = None
                self.state.reset()
                self.status = 'connecting'
                self.counters['connection_attempts'] += 1
                try:
                    self._publish()
                    await source.open()
                    self._connection_opened_ns = self._clock()
                    self.status = 'connected'
                    self.last_error = None
                    self.counters['connections'] += 1
                    self.polling.connected()
                    self._observe('stream_gap', self._clock(), reason='connection_open')
                    self._publish()
                    while True:
                        data = await source.read()
                        now = self._clock()
                        if data == b'':
                            raise EOFError('TCP peer closed the stream')
                        if data is not None:
                            
                            
                            if (self._last_rx_ns is not None and self._parser.buffer
                                    and now - self._last_rx_ns > min(self.state.stale_after_ns, self.PARTIAL_FRAME_NS)):
                                self._observe('stream_gap', now, reason='partial_frame_timeout')
                                self._finish()
                                self.polling.stream_gap('partial_frame_timeout', now)
                            self._last_rx_ns = now
                            if self._feed(data, now):
                                delay = self._retry_initial
                                self._last_valid_frame_ns = now
                                self._connection_failures = 0
                        elif (self._last_rx_ns is not None and self._parser.buffer
                              and now - self._last_rx_ns > min(self.state.stale_after_ns, self.PARTIAL_FRAME_NS)):
                            self._observe('stream_gap', now, reason='partial_frame_timeout')
                            self._finish()
                            self.polling.stream_gap('partial_frame_timeout', now)
                        if isinstance(self.config, TcpConfig):
                            last_frame = (self._last_valid_frame_ns if self._last_valid_frame_ns is not None
                                          else self._connection_opened_ns)
                            if now - last_frame > self.state.stale_after_ns:
                                self.counters['stale_reconnects'] += 1
                                self._observe('stream_gap', now, reason='tcp_stale_timeout')
                                _LOGGER.warning('No valid C14 frame over TCP for %.1f seconds; reconnecting',
                                                (now - last_frame) / 1e9)
                                raise TimeoutError('No valid C14 frame within stale_after')
                        if self._pending_tx is None:
                            self._pending_tx = self.polling.idle(now,
                                stream_idle=not self._parser.buffer and self._last_rx_ns is not None
                                and now-self._last_rx_ns > 300_000_000,
                                quiet_ns=(now-self._last_rx_ns if not self._parser.buffer
                                          and self._last_rx_ns is not None else None))
                        await self._transmit(source)
                        self._publish()
                except (OSError, EOFError) as error:
                    self.last_error = f'{type(error).__name__}: {error}'
                    if isinstance(self.config, TcpConfig):
                        self._connection_failures += 1
                    self._retry_delay = (self.TCP_SLOW_RETRY_SECONDS
                        if isinstance(self.config, TcpConfig) and self._connection_failures >= self.TCP_FAILURE_LIMIT
                        else delay)
                finally:
                    try:
                        await source.close()
                    except OSError as error:
                        self.last_error = f'{type(error).__name__}: {error}'
                    finally:
                        self._observe('stream_gap', self._clock(), reason='connection_closed')
                        self._finish()
                        self.state.reset()
                        self._pending_tx = None
                        self.polling.disconnected()
                self.status = 'retrying'
                self._publish()
                await self._sleep(self._retry_delay)
                delay = min(delay * 2, self._retry_max)
        finally:
            self.status = 'stopped'
            self._running = False
            self.state.reset()
            self._publish()
