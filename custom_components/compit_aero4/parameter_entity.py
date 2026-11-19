"""Shared availability and confirmed-setting semantics for catalog entities."""
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import Aero4Entity
from .c14.commands import CommandError
from .c14.parameters import PARAMETERS

SPECIAL_CONTROLS = {'bypass', 'boost', 'ventilation_work_mode'}
OPERATIONAL_SETTINGS = {'manual_temperature', 'ventilation_enabled', 'away_mode', 'holiday_mode',
                        'fireplace_active', 'thermostat_mode', 'installation_season', 'gwc_mode'}


def parameter_category(parameter):
    return None if parameter.key in OPERATIONAL_SETTINGS else EntityCategory.CONFIG


class Aero4ParameterEntity(Aero4Entity):
    @property
    def parameter(self):
        return PARAMETERS[self.entity_description.key.removeprefix('parameter_')]

    @property
    def info(self):
        return self.coordinator.data['fields'][self.parameter.field]

    @property
    def available(self):
        data = self.coordinator.data
        return (super().available and data['transport']['connected'] and self.info['status'] == 'known'
                and data['aero_online'] and data['polling']['enabled']
                and data['polling']['status'] in ('ready', 'polling')
                and self.coordinator.receiver.polling.extended_parameters)

    @property
    def extra_state_attributes(self):
        command = self.coordinator.data['command']
        return {**(super().extra_state_attributes or {}),
                'confirmation': 'stored_parameter',
                'pending': command['key'] == self.parameter.key and command['status'] in ('queued', 'waiting')}

    async def async_write_value(self, value):
        try:
            await self.coordinator.receiver.async_set_parameter(self.parameter.key, value)
        except (ValueError, KeyError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key='invalid_parameter_value') from error
        except CommandError as error:
            key = {'busy': 'command_busy', 'control_unavailable': 'control_unavailable'}.get(
                str(error), 'command_not_confirmed')
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=key) from error
