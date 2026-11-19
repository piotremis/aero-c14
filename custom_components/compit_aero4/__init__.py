"""Local AERO C14 integration with optional read polling."""
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryError
from .coordinator import Aero4Coordinator
from .settings import endpoint_key
from .services import async_register_services
from .frontend import async_register_cards

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.SELECT, Platform.NUMBER, Platform.BUTTON]


async def async_setup(hass, config):
    await async_register_cards(hass)
    async_register_services(hass)
    return True


async def async_setup_entry(hass, entry):
    try:
        key = endpoint_key(entry.data)
        if any(other.entry_id != entry.entry_id and
               getattr(other, 'runtime_data', None) is not None and
               endpoint_key(other.data) == key for other in hass.config_entries.async_entries(entry.domain)):
            raise ConfigEntryError('This endpoint is already in use by another AERO 4 entry')
        coordinator = Aero4Coordinator(hass, entry)
    except (KeyError, ValueError, TypeError) as error:
        raise ConfigEntryError('Invalid AERO 4 configuration; reconfigure the entry') from error
    entry.runtime_data = coordinator
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        coordinator.async_start()
    except BaseException:
        await coordinator.async_stop()
        entry.runtime_data = None
        raise
    return True


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
        entry.runtime_data = None
    return unloaded
