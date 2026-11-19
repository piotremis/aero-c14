"""Explicit maintenance action; no reset on setup, reconnect or ordinary reads."""
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.helpers.entity import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from .c14.commands import CommandError
from .const import DOMAIN
from .entity import Aero4Entity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get('extended_parameters',False):
        async_add_entities([Aero4FilterResetButton(entry.runtime_data,ButtonEntityDescription(
            key='filter_reset',translation_key='filter_reset',icon='mdi:air-filter',
            entity_category=EntityCategory.CONFIG))])
    async_add_entities([Aero4ClockSyncButton(entry.runtime_data,ButtonEntityDescription(
        key='clock_sync',translation_key='clock_sync',icon='mdi:clock-sync',
        entity_category=EntityCategory.CONFIG))])


class Aero4ClockSyncButton(Aero4Entity, ButtonEntity):
    @property
    def available(self):
        data = self.coordinator.data
        return (super().available and data['transport']['connected'] and data['aero_online']
                and data['polling']['enabled'] and data['polling']['status'] in ('ready','polling'))

    async def async_press(self):
        try:
            await self.coordinator.async_sync_clock()
        except CommandError as error:
            reason={'busy':'command_busy','control_unavailable':'control_unavailable'}.get(str(error),'command_not_confirmed')
            raise HomeAssistantError(translation_domain=DOMAIN,translation_key=reason) from error


class Aero4FilterResetButton(Aero4Entity,ButtonEntity):
    @property
    def available(self):
        data=self.coordinator.data
        return (super().available and data['transport']['connected'] and data['aero_online']
                and data['polling']['enabled'] and data['polling']['status'] in ('ready','polling')
                and self.coordinator.receiver.polling.extended_parameters
                and data['fields']['parameter_filter_elapsed_days']['status']=='known')

    @property
    def extra_state_attributes(self):
        command=self.coordinator.data['command']
        return {'pending':command['key']=='filter_reset' and command['status'] in ('queued','waiting')}

    async def async_press(self):
        try:
            await self.coordinator.receiver.async_reset_filter_counter()
        except CommandError as error:
            reason={'busy':'command_busy','control_unavailable':'control_unavailable'}.get(str(error),'command_not_confirmed')
            raise HomeAssistantError(translation_domain=DOMAIN,translation_key=reason) from error
