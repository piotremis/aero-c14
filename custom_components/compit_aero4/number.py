"""Home Assistant numeric settings."""
from decimal import Decimal, ROUND_HALF_UP
from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode, NumberDeviceClass
from .parameter_entity import Aero4ParameterEntity, parameter_category
from .c14.parameters import PARAMETERS


async def async_setup_entry(hass, entry, async_add_entities):
    if not entry.data.get('extended_parameters', False):
        return
    async_add_entities([
        Aero4ParameterNumber(entry.runtime_data, NumberEntityDescription(
            key=p.field, translation_key=p.key, entity_category=parameter_category(p),
            native_min_value=p.minimum, native_max_value=p.maximum, native_step=p.step,
            native_unit_of_measurement=p.unit, mode=NumberMode.BOX,
            device_class=NumberDeviceClass.TEMPERATURE if p.unit == '°C' and not p.temperature_delta else None,
            icon='mdi:thermometer' if p.unit == '°C' else 'mdi:tune'))
        for p in PARAMETERS.values() if p.category == 'setting' and p.writable and not p.options
    ])


class Aero4ParameterNumber(Aero4ParameterEntity, NumberEntity):
    @property
    def native_value(self):
        return self.info['value']

    async def async_set_native_value(self, value):
        if self.native_unit_of_measurement == '°C' and self.unit_of_measurement != '°C':


            p = self.parameter
            step = Decimal(str(p.step))
            origin = Decimal(str(p.minimum))
            steps = ((Decimal(str(value)) - origin) / step).to_integral_value(rounding=ROUND_HALF_UP)
            value = float(origin + steps * step)
        await self.async_write_value(value)
