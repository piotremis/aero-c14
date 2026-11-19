"""Diagnostics omit local endpoints, names, raw captures and OS error messages."""
from copy import deepcopy
from homeassistant.components.diagnostics import async_redact_data


async def async_get_config_entry_diagnostics(hass, entry):
    snapshot = deepcopy(entry.runtime_data.data)
    snapshot['transport'].pop('last_error', None)
    capture=entry.runtime_data.capture
    return {'configuration': async_redact_data(dict(entry.data), {'host', 'serial_port', 'name'}),
            'snapshot': snapshot,
            'capture':capture.snapshot() if capture is not None else {'active':False,'state':'not_started'}}
