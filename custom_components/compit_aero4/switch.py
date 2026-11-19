"""Bypass control reports actual AERO state; requests never predict success."""
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.exceptions import HomeAssistantError

from .c14.commands import CommandError
from .const import DOMAIN
from .entity import Aero4Entity
from .parameter_entity import Aero4ParameterEntity, SPECIAL_CONTROLS, parameter_category
from .c14.parameters import PARAMETERS


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Aero4ControlSwitch(entry.runtime_data,description) for description in (
        SwitchEntityDescription(key='bypass_control',translation_key='bypass_control',icon='mdi:valve'),
        SwitchEntityDescription(key='boost_control',translation_key='boost_control',icon='mdi:weather-windy'))])
    async_add_entities([
        Aero4ParameterSwitch(entry.runtime_data, SwitchEntityDescription(
            key=p.field, translation_key=p.key, entity_category=parameter_category(p), icon='mdi:toggle-switch'))
        for p in PARAMETERS.values() if entry.data.get('extended_parameters', False)
        and p.category == 'setting' and p.options and p.key not in SPECIAL_CONTROLS
        and all(type(value) is bool for _, value in p.options)
    ])


    async_add_entities([
        Aero4LedFlagSwitch(entry.runtime_data, SwitchEntityDescription(
            key=p.field+'_'+flag, translation_key=p.key+'_'+flag,
            entity_category=parameter_category(p), icon='mdi:led-on'))
        for p in PARAMETERS.values() if entry.data.get('extended_parameters', False)
        and p.key.endswith('_led_mode') for flag in LED_FLAGS
    ])


LED_FLAGS = {'standby': 1, 'thermostat': 2, 'sensors': 4}


class Aero4LedFlagSwitch(Aero4ParameterEntity, SwitchEntity):
    @property
    def flag(self):
        return self.entity_description.key.rsplit('_', 1)[1]

    @property
    def parameter(self):
        return PARAMETERS[self.entity_description.key.removeprefix('parameter_').rsplit('_', 1)[0]]

    @property
    def is_on(self):
        if self.info['status'] != 'known':
            return None
        return bool(self.parameter.encode(self.info['value']) & LED_FLAGS[self.flag])

    async def _set_flag(self, enabled):
        if not self.available:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key='control_unavailable')
        try:
            await self.coordinator.receiver.async_set_led_flag(self.parameter.key, LED_FLAGS[self.flag], enabled)
        except (ValueError, KeyError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key='invalid_parameter_value') from error
        except CommandError as error:
            key = {'busy': 'command_busy', 'control_unavailable': 'control_unavailable'}.get(
                str(error), 'command_not_confirmed')
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=key) from error

    async def async_turn_on(self, **kwargs):
        await self._set_flag(True)

    async def async_turn_off(self, **kwargs):
        await self._set_flag(False)


class Aero4ParameterSwitch(Aero4ParameterEntity, SwitchEntity):
    @property
    def is_on(self):
        return self.info['value']

    async def async_turn_on(self, **kwargs):
        await self.async_write_value(True)

    async def async_turn_off(self, **kwargs):
        await self.async_write_value(False)


class Aero4ControlSwitch(Aero4Entity, SwitchEntity):
    _attr_assumed_state = False

    @property
    def control_key(self):
        return self.entity_description.key.removesuffix('_control')

    @property
    def control_fields(self):
        return (('bypass_requested','bypass_reported_open') if self.control_key=='bypass'
                else ('boost_requested','boost_active'))

    @property
    def available(self):
        data = self.coordinator.data
        return (super().available and data['transport']['connected'] and data['aero_online']
                and data['polling']['enabled'] and data['polling']['status'] in ('ready', 'polling')
                and all(data['fields'][key]['status'] == 'known'
                        for key in self.control_fields))

    @property
    def is_on(self):
        return self.coordinator.data['fields'][self.control_fields[1]]['value']

    @property
    def extra_state_attributes(self):
        command = self.coordinator.data['command']
        attributes = {'pending': command['key']==self.control_key and command['status'] in ('queued', 'waiting')}
        if self.control_key == 'boost':
            timer = self.coordinator.data.get('boost_timer', {})
            attributes['control_queue'] = self.coordinator.data.get('control_queue', {})
            attributes.update(boost_deadline=timer.get('deadline'),
                              boost_timer_status=timer.get('status', 'idle'),
                              boost_timer_error=timer.get('error'))
        return attributes

    async def _set(self, enabled):
        try:
            request=(self.coordinator.receiver.async_set_bypass if self.control_key=='bypass'
                     else self.coordinator.receiver.async_set_boost)
            await request(enabled)
        except CommandError as error:
            reason = str(error)
            key = {'busy':'command_busy', 'control_unavailable':'control_unavailable'}.get(
                reason, 'command_not_confirmed')
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=key) from error

    async def async_turn_on(self, **kwargs):
        await self._set(True)

    async def async_turn_off(self, **kwargs):
        await self._set(False)
