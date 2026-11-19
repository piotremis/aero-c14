"""Separate operating mode from the manual gear, despite combined wire codes."""
from homeassistant.components.select import SelectEntity,SelectEntityDescription
from homeassistant.exceptions import HomeAssistantError
from .entity import Aero4Entity
from .const import DOMAIN
from .c14.commands import CommandError,VENTILATION_VALUES
from .parameter_entity import Aero4ParameterEntity, SPECIAL_CONTROLS, parameter_category
from .c14.parameters import PARAMETERS

MANUAL_GEARS=('B1', 'B2', 'B3', 'stopped')


async def async_setup_entry(hass,entry,async_add_entities):
    if entry.data.get('extended_parameters', False):
        async_add_entities([Aero4BypassModeSelect(entry.runtime_data, SelectEntityDescription(
            key='bypass_mode', translation_key='bypass_mode', options=['OFF', 'AUTO', 'ON'], icon='mdi:valve'))])
    async_add_entities([Aero4VentilationSelect(entry.runtime_data,description) for description in (
        SelectEntityDescription(key='operating_mode',translation_key='operating_mode',
                                options=['manual','schedule'] + (['holiday_schedule'] if entry.data.get('extended_parameters', False) else []),icon='mdi:calendar-clock'),
        SelectEntityDescription(key='manual_speed',translation_key='manual_speed',
                                options=list(MANUAL_GEARS if entry.data.get('extended_parameters', False) else MANUAL_GEARS[:3]),icon='mdi:fan'))])
    async_add_entities([
        Aero4ParameterSelect(entry.runtime_data, SelectEntityDescription(
            key=p.field, translation_key=p.key, options=[value for _, value in p.options],
            entity_category=parameter_category(p), icon='mdi:tune'))
        for p in PARAMETERS.values() if entry.data.get('extended_parameters', False)
        and p.category == 'setting' and p.options and p.key not in SPECIAL_CONTROLS
        and all(isinstance(value, str) for _, value in p.options)
    ])


class Aero4ParameterSelect(Aero4ParameterEntity, SelectEntity):
    @property
    def current_option(self):
        return self.info['value']

    async def async_select_option(self, option):
        await self.async_write_value(option)


class Aero4BypassModeSelect(Aero4Entity, SelectEntity):
    @property
    def available(self):
        data = self.coordinator.data
        return (super().available and data['transport']['connected'] and data['aero_online']
                and data['polling']['enabled'] and data['polling']['status'] in ('ready', 'polling')
                and all(data['fields'][key]['status'] == 'known' for key in ('bypass_requested', 'bypass_readback'))
                and data['fields']['bypass_requested']['value'] == data['fields']['bypass_readback']['value'])

    @property
    def current_option(self):
        return self.coordinator.data['fields']['bypass_readback']['value']

    async def async_select_option(self, option):
        try:
            await self.coordinator.receiver.async_set_bypass_mode(option)
        except ValueError as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key='invalid_parameter_value') from error
        except CommandError as error:
            key = {'busy': 'command_busy', 'control_unavailable': 'control_unavailable'}.get(str(error), 'command_not_confirmed')
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=key) from error


class Aero4VentilationSelect(Aero4Entity,SelectEntity):
    @property
    def _selection(self):
        fields=self.coordinator.data['fields']
        readback=fields['ventilation_mode_readback']
        
        
        return readback['value'] if readback['status']=='known' else None

    @property
    def available(self):
        data=self.coordinator.data
        return (super().available and data['transport']['connected'] and data['aero_online']
                and data['polling']['enabled'] and data['polling']['status'] in ('ready','polling')
                and self.current_option is not None
                and (self.entity_description.key=='operating_mode' or self._selection in self.options))

    @property
    def current_option(self):
        if self.entity_description.key=='manual_speed':
            return self._selection if self._selection in self.options else None
        option = 'manual' if self._selection in MANUAL_GEARS else self._selection if self._selection in ('schedule', 'holiday_schedule') else None
        return option if option in self.options else None

    async def async_select_option(self,option):
        if option not in self.options:
            raise HomeAssistantError(translation_domain=DOMAIN,translation_key='control_unavailable')
        if self.entity_description.key=='manual_speed':
            if self._selection not in MANUAL_GEARS:
                raise HomeAssistantError(translation_domain=DOMAIN,translation_key='manual_mode_required')
            selection=option
        elif option=='manual':
            
            field=self.coordinator.data['fields']['ventilation_requested']
            if field['status']!='known' or field['value'] not in MANUAL_GEARS:
                raise HomeAssistantError(translation_domain=DOMAIN,translation_key='manual_gear_unknown')
            selection=field['value']
        else:
            selection=option
        try:
            await self.coordinator.receiver.async_set_ventilation(selection)
        except CommandError as error:
            key={'busy':'command_busy','control_unavailable':'control_unavailable'}.get(str(error),'command_not_confirmed')
            raise HomeAssistantError(translation_domain=DOMAIN,translation_key=key) from error
