"""C14 parameter definitions, validation and encoding."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .protocol import checksum_sum7
from .parameter_catalog import CATALOG


@dataclass(frozen=True)
class Parameter:
    key: str
    address: int
    scale: int = 1
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: tuple = ()
    unit: str | None = None
    category: str = 'setting'
    temperature_delta: bool = False
    multiplier: int = 1
    disabled_at: float | None = None

    @property
    def field(self):
        return 'parameter_' + self.key

    @property
    def writable(self):
        return bool(self.options) or self.minimum is not None and self.step is not None

    def decode(self, integer):
        if type(integer) is not int:
            return None
        if self.key == 'filter_elapsed_days' and (integer < 0 or integer == 9999):
            
            
            return None
        if self.options:
            return dict(self.options).get(integer)
        value = integer * self.multiplier / self.scale
        if self.unit == '°C' and not -50 <= value <= 100:
            return None  
        if self.minimum is not None and not self.minimum <= value <= self.maximum:
            return None
        return integer * self.multiplier if self.scale == 1 else value

    def encode(self, value):
        if not self.writable:
            raise ValueError('Parameter has no verified editor bounds')
        if self.options:
            for wire, option in self.options:
                if type(value) is type(option) and value == option:
                    return wire
            raise ValueError('Unsupported parameter option')
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError('Parameter requires a finite number')
        try:
            decimal = Decimal(str(value))
            if type(value) is float and decimal.is_finite():


                scaled = decimal * self.scale / self.multiplier
                nearest = scaled.to_integral_value()
                if abs(scaled - nearest) <= Decimal('0.0000001'):
                    decimal = nearest * self.multiplier / self.scale
            if not decimal.is_finite() or not Decimal(str(self.minimum)) <= decimal <= Decimal(str(self.maximum)):
                raise ValueError('Parameter outside observed editor range')
            if (decimal - Decimal(str(self.minimum))) % Decimal(str(self.step)):
                raise ValueError('Parameter does not match observed editor step')
            integer = decimal * self.scale / self.multiplier
            if integer != integer.to_integral_value():
                raise ValueError('Parameter is not representable on the wire')
            return int(integer)
        except InvalidOperation as error:
            raise ValueError('Invalid parameter number') from error


PARAMETERS = {
    item['key']: Parameter(
        key=item['key'], address=int(item['address'], 16), scale=item.get('wire_scale', 1),
        minimum=item.get('ui_range', [None, None])[0],
        maximum=item.get('ui_range', [None, None])[1], step=item.get('ui_step'),
        options=tuple((int(wire), value) for wire, value in item.get('options', {}).items()),
        unit=item.get('unit'),
        temperature_delta=item.get('temperature_delta', False),
        disabled_at=item.get('disabled_at'),
        multiplier=item.get('wire_multiplier', 1),
    ) for item in CATALOG
}
SCHEDULE_DAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'holiday')
for day_index, day in enumerate(SCHEDULE_DAYS):
    for period in range(1, 4):
        for boundary_index, boundary in enumerate(('start', 'end')):
            key = f'schedule_{day}_{period}_{boundary}'
            PARAMETERS[key] = Parameter(
                key=key, address=0x022D + 7 * day_index + 2 * (period - 1) + boundary_index,
                options=tuple((unit, f'{unit // 4:02d}:{unit % 4 * 15:02d}')
                              for unit in range(97 if boundary == 'end' else 96)),
                category='schedule',
            )
BY_ADDRESS = {f'{parameter.address:04X}': parameter for parameter in PARAMETERS.values()}


def build_parameter_write(key, value):
    parameter = PARAMETERS[key]
    integer = parameter.encode(value)
    high, low = divmod(integer + 2000, 128)
    if not 0 <= high < 128:
        raise ValueError('Parameter outside wire range')
    raw = bytearray(30)
    raw[0], raw[1], raw[3], raw[29] = 0xA9, 0x57, 0x70, 0x23
    raw[5:9] = parameter.address.to_bytes(2, 'big') + bytes((high, low))
    raw[2] = checksum_sum7(raw)
    return bytes(raw)


CARD_PARAMETER_KEYS = ('ventilation_enabled', 'gwc_mode', 'fireplace_active',
                       'holiday_mode', 'away_mode', 'boost_duration', 'filter_reminder_period')


def additional_batches(base_batches):
    """Card first, complete schedule second, then remaining configuration."""
    existing = {address for batch in base_batches for address in batch}
    card = [PARAMETERS[key].address for key in CARD_PARAMETER_KEYS
            if PARAMETERS[key].address not in existing]
    schedule = [p.address for p in PARAMETERS.values() if p.category == 'schedule'
                and p.address not in existing]
    remaining = [p.address for p in PARAMETERS.values()
                 if p.address not in existing and p.address not in card + schedule]
    fill = min((-len(card)) % 6, len(remaining))
    card.extend(remaining[:fill])
    remaining = remaining[fill:]
    return tuple(tuple(group[offset:offset+6]) for group in (card, schedule, remaining)
                 for offset in range(0, len(group), 6))


def build_filter_counter_reset():
    """Fixed supported W0055=0 action; no arbitrary counter-value encoder."""
    raw = bytearray(30)
    raw[0], raw[1], raw[3], raw[29] = 0xA9, 0x57, 0x70, 0x23
    raw[5:9] = bytes.fromhex('00 55 0f 50')
    raw[2] = checksum_sum7(raw)
    return bytes(raw)
