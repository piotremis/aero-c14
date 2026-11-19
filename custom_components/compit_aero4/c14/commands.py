"""Bounded control operations; all wire scheduling remains in LocalPolling."""
from dataclasses import dataclass, field

from .protocol import checksum_sum7


class CommandError(RuntimeError):
    """A fixed, endpoint-free reason suitable for diagnostics and HA errors."""


def build_bypass_write(enabled: bool) -> bytes:
    """Encode only the two supported, supported bypass values."""
    return _build_toggle(0x4F, enabled, 2)


def build_boost_write(enabled: bool) -> bytes:
    """Encode the supported 0051 ventilation boost ON/OFF command."""
    return _build_toggle(0x51, enabled, 1)


VENTILATION_VALUES = {'stopped':0,'B1':1,'B2':2,'B3':3,'holiday_schedule':4,'schedule':5}


def build_ventilation_write(selection):
    if not isinstance(selection,str) or selection not in VENTILATION_VALUES:
        raise ValueError('Unsupported ventilation selection')
    raw=bytearray(30)
    raw[0],raw[1],raw[3],raw[29]=0xA9,0x57,0x70,0x23
    raw[5:9]=bytes((0,0x50,0x0F,0x50+VENTILATION_VALUES[selection]))
    raw[2]=checksum_sum7(raw)
    return bytes(raw)


def _build_toggle(address, enabled, on_value):
    if type(enabled) is not bool:
        raise ValueError('Control requires a boolean')
    raw = bytearray(30)
    raw[0], raw[1], raw[3], raw[29] = 0xA9, 0x57, 0x70, 0x23
    raw[5:9] = bytes((0, address, 0x0F, 0x50 + (on_value if enabled else 0)))
    raw[2] = checksum_sum7(raw)
    return bytes(raw)


@dataclass
class BypassOperation:
    direct_forwarded = False
    key = 'bypass'
    address = '004F'
    on_value = 2
    confirmation_batch = 0
    readback_key = 'bypass_readback'
    requested_key = 'bypass_requested'
    reported_key = 'bypass_reported_open'

    enabled: bool
    queued_ns: int
    stale_ns: int
    status: str = 'queued'
    error: str | None = None
    sent_ns: int | None = None
    echoed: bool = False
    write_closed: bool = False
    confirmations: dict = field(default_factory=dict)
    finished_ns: int | None = None

    @property
    def wire_value(self):
        return self.on_value if self.enabled else 0

    def packet(self):
        return build_bypass_write(self.enabled)

    def expected_values(self):
        if self.direct_forwarded:
            return {self.readback_key:'ON' if self.enabled else 'OFF', self.reported_key:self.enabled}
        return {self.readback_key:'ON' if self.enabled else 'OFF',
                self.requested_key:'ON' if self.enabled else 'OFF',self.reported_key:self.enabled}

    @property
    def pending(self):
        return self.status in ('queued', 'waiting')

    def fail(self, reason, now=None):
        if self.pending:
            self.status, self.error, self.finished_ns = 'failed', reason, now

    def sent(self, now):
        
        self.sent_ns = now
        if self.pending:
            self.status = 'waiting'

    def observe(self, values, now):
        if not self.pending or self.sent_ns is None or now <= self.sent_ns:
            return
        if 'bypass_reported_open' in values:
            self.confirmations['direct_aero_observed'] = (True, now)
        for key in (self.requested_key, self.reported_key):
            if key in values:
                self.confirmations[key] = (values[key], now)

    def readback(self, value, observed_ns):
        if self.pending and self.sent_ns is not None and observed_ns > self.sent_ns:
            self.confirmations[self.readback_key] = (value, observed_ns)

    def tick(self, now, *, can_complete=False):
        if not self.pending:
            return
        deadline = (self.queued_ns + 60_000_000_000 if self.sent_ns is None
                    else self.sent_ns + 120_000_000_000)
        if now >= deadline:
            self.fail('window_unavailable' if self.sent_ns is None else 'confirmation_timeout', now)
            return
        expected = self.expected_values()
        if (can_complete and self.echoed and self.write_closed
                and all(key in self.confirmations and self.confirmations[key][0] == value
                        and 0 <= now - self.confirmations[key][1] <= self.stale_ns
                        for key, value in expected.items())):
            self.status, self.finished_ns = 'succeeded', now

    def snapshot(self):
        return {'key':self.key,'status': self.status, 'requested': 'ON' if self.enabled else 'OFF',
                'error': self.error, 'sent': self.sent_ns is not None,
                'echoed': self.echoed, 'write_closed': self.write_closed,
                **({'direct_forwarded':True} if self.direct_forwarded else {})}


class BoostOperation(BypassOperation):
    key = 'boost'
    address = '0051'
    on_value = 1
    confirmation_batch = 1
    readback_key = 'boost_readback'
    requested_key = 'boost_requested'
    reported_key = 'boost_active'
    direct_forwarded = False

    def packet(self):
        return build_boost_write(self.enabled)

    def expected_values(self):
        keys=(self.readback_key,self.reported_key) if self.direct_forwarded else (self.readback_key,self.requested_key,self.reported_key)
        return {key:self.enabled for key in keys}

    def snapshot(self):
        return {**super().snapshot(),'direct_forwarded':self.direct_forwarded}


class BypassModeOperation(BypassOperation):
    """AUTO confirms the mode, whose actual opening depends on conditions."""
    @property
    def wire_value(self):
        return {'OFF': 0, 'AUTO': 1, 'ON': 2}[self.enabled]

    def packet(self):
        from .parameters import build_parameter_write
        return build_parameter_write('bypass', self.enabled.lower())

    def expected_values(self):
        expected = {self.readback_key: self.enabled}
        if not self.direct_forwarded:expected[self.requested_key] = self.enabled
        if self.direct_forwarded and self.enabled == 'AUTO':expected['direct_aero_observed'] = True
        if self.enabled != 'AUTO':
            expected[self.reported_key] = self.enabled == 'ON'
        return expected

    def snapshot(self):
        return {**super().snapshot(), 'requested': self.enabled,
                'confirmation': 'requested_mode' if self.enabled == 'AUTO' else 'reported_output'}


class VentilationOperation(BypassOperation):
    """The wire combines manual gear selection and return-to-schedule."""
    direct_forwarded = False
    stored_only = False
    key='ventilation'
    address='0050'
    confirmation_batch=1
    readback_key='ventilation_mode_readback'
    requested_key='ventilation_mode_requested'
    reported_key='ventilation_requested'

    @property
    def wire_value(self):
        return VENTILATION_VALUES[self.enabled]

    def packet(self):
        return build_ventilation_write(self.enabled)

    def expected_values(self):
        if self.stored_only:return {self.readback_key:self.enabled}
        if self.direct_forwarded:
            return {self.readback_key: self.enabled, 'ventilation_reported_level': self.enabled}
        expected={self.readback_key:self.enabled}
        if self.enabled != 'holiday_schedule':
            expected[self.requested_key] = self.enabled
        if self.enabled in ('stopped', 'B1', 'B2', 'B3'):expected[self.reported_key]=self.enabled
        return expected

    def observe(self, values, now):
        super().observe(values, now)
        if self.pending and self.sent_ns is not None and now > self.sent_ns and 'ventilation_reported_level' in values:
            self.confirmations['ventilation_reported_level'] = (values['ventilation_reported_level'], now)

    def snapshot(self):
        return {**super().snapshot(),'requested':self.enabled,'direct_forwarded':self.direct_forwarded,
                'confirmation': 'stored_parameter' if self.stored_only or self.enabled == 'holiday_schedule' else 'requested_level'}


class ParameterOperation(BypassOperation):
    """Confirm stored configuration; do not claim a physical output changed."""

    def __init__(self, parameter, value, queued_ns, stale_ns, confirmation_batch):
        
        
        canonical = parameter.decode(parameter.encode(value))
        if canonical is None:
            raise ValueError('Parameter value cannot be read back reliably')
        super().__init__(canonical, queued_ns, stale_ns)
        self.parameter = parameter
        self.key = parameter.key
        self.address = f'{parameter.address:04X}'
        self.readback_key = parameter.field
        self.confirmation_batch = confirmation_batch

    @property
    def wire_value(self):
        return self.parameter.encode(self.enabled)

    def packet(self):
        from .parameters import build_parameter_write
        return build_parameter_write(self.key, self.enabled)

    def observe(self, values, now):
        
        
        return

    def expected_values(self):
        return {self.readback_key: self.enabled}

    def snapshot(self):
        return {**super().snapshot(), 'requested': self.enabled,
                'confirmation': 'stored_parameter'}


class DirectParameterOperation(ParameterOperation):
    """Conditional GWC AUTO confirms delivery, not a forced physical output."""
    def observe(self, values, now):
        if not self.pending or self.sent_ns is None or now <= self.sent_ns:return
        if self.key == 'fireplace_active' and 'fan_a_percent' in values and 'fan_b_percent' in values:
            self.confirmations['direct_aero_observed'] = (True, now)
        if self.key == 'gwc_mode' and 'gwc_reported_active' in values:
            self.confirmations['direct_aero_observed'] = (True, now)
            self.confirmations['gwc_reported_active'] = (values['gwc_reported_active'], now)

    def expected_values(self):
        expected=super().expected_values()
        if self.direct_forwarded:
            expected['direct_aero_observed']=True
            if self.enabled=='off':expected['gwc_reported_active']=False
        return expected


class PowerOperation(DirectParameterOperation):
    resume_level = None
    @property
    def reported_level(self):return self.resume_level if self.enabled else 'stopped'
    def observe(self, values, now):
        if self.pending and self.sent_ns is not None and now > self.sent_ns and 'ventilation_reported_level' in values:
            self.confirmations['ventilation_reported_level']=(values['ventilation_reported_level'],now)
    def expected_values(self):
        expected=ParameterOperation.expected_values(self)
        if self.direct_forwarded:
            expected['ventilation_reported_level']=self.reported_level
        return expected


class HolidayOperation(PowerOperation):
    @property
    def reported_level(self):return 'stopped' if self.enabled else self.resume_level


class LedFlagOperation(ParameterOperation):
    """Merge one flag with a requested read inside our owned write window."""

    def __init__(self, parameter, bit, enabled, queued_ns, stale_ns, confirmation_batch):
        if (not parameter.key.endswith('_led_mode') or bit not in (1, 2, 4)
                or type(bit) is not int or type(enabled) is not bool
                or {wire for wire, _ in parameter.options} != set(range(8))):
            raise ValueError('Choose a mapped LED flag')
        super().__init__(parameter, dict(parameter.options)[0], queued_ns, stale_ns, confirmation_batch)
        self.bit, self.flag_enabled = bit, enabled
        self.prepared = False

    def prepare_from_read(self, value):
        current = self.parameter.encode(value)
        updated = current | self.bit if self.flag_enabled else current & ~self.bit
        self.enabled = dict(self.parameter.options)[updated]
        self.prepared = True

    def packet(self):
        if not self.prepared:
            raise RuntimeError('LED write requires its own fresh read')
        return super().packet()

    def snapshot(self):
        return {**super().snapshot(), 'requested': self.enabled if self.prepared else None,
                'flag_bit': self.bit, 'flag_enabled': self.flag_enabled,
                'fresh_read_received': self.prepared}


class FilterResetOperation(BypassOperation):
    """Confirm the stored counter is zero; never claim a filter was replaced."""
    key = 'filter_reset'
    address = '0055'
    readback_key = 'parameter_filter_elapsed_days'

    def __init__(self, queued_ns, stale_ns, confirmation_batch):
        super().__init__(0, queued_ns, stale_ns)
        self.confirmation_batch = confirmation_batch

    def packet(self):
        from .parameters import build_filter_counter_reset
        return build_filter_counter_reset()

    def observe(self, values, now):
        return  

    def expected_values(self):
        return {self.readback_key: 0}

    def snapshot(self):
        return {**super().snapshot(), 'requested':0, 'confirmation':'stored_parameter'}


class ParameterRefreshOperation(BypassOperation):
    """A priority read on the same owner/queue, never a write request."""
    key = 'parameter_refresh'
    requires_write = False

    def __init__(self, parameter, queued_ns, stale_ns, confirmation_batch):
        super().__init__(None, queued_ns, stale_ns)
        self.parameter = parameter
        self.address = f'{parameter.address:04X}'
        self.readback_key = parameter.field
        self.confirmation_batch = confirmation_batch
        self.read_closed = False

    def packet(self):
        raise RuntimeError('A refresh must never enter the write path')

    def observe(self, values, now):
        return

    def tick(self, now, *, can_complete=False):
        if not self.pending:
            return
        deadline = self.queued_ns + 60_000_000_000 if self.sent_ns is None else self.sent_ns + 120_000_000_000
        if now >= deadline:
            self.fail('window_unavailable' if self.sent_ns is None else 'confirmation_timeout', now)
        elif (can_complete and self.read_closed and self.readback_key in self.confirmations
              and 0 <= now - self.confirmations[self.readback_key][1] <= self.stale_ns):
            self.status, self.finished_ns = 'succeeded', now

    def snapshot(self):
        return {**super().snapshot(), 'requested': None, 'kind': 'read',
                'target': self.parameter.key, 'confirmation': 'received_parameter',
                'read_closed': self.read_closed}
