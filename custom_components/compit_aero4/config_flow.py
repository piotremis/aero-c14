"""UI transport configuration and explicit opt-in to local read polling."""
from uuid import uuid4
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from .const import (
    DOMAIN, DEFAULT_NAME, CONF_TRANSPORT, CONF_SERIAL_PORT, CONF_TCP_PORT,
    CONF_BAUD, CONF_STOPBITS, CONF_STALE_AFTER, CONF_CONNECT_TIMEOUT, CONF_LOCAL_POLLING,
)
from .settings import endpoint_key, transport_config


class Aero4ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id='user', menu_options=['serial', 'tcp'])

    async def async_step_reconfigure(self, user_input=None):
        return self.async_show_menu(step_id='reconfigure', menu_options=['serial', 'tcp'])

    def _entry(self):
        return self._get_reconfigure_entry() if self.source == 'reconfigure' else None

    def _schema(self, kind):
        entry = self._entry()
        defaults = dict(entry.data) if entry else {}
        fields = {vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str}
        if kind == 'serial':
            port = ({'default': defaults[CONF_SERIAL_PORT]} if CONF_SERIAL_PORT in defaults else {})
            fields.update({vol.Required(CONF_SERIAL_PORT, **port): str,
                vol.Required(CONF_BAUD, default=defaults.get(CONF_BAUD, 9600)): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Required(CONF_STOPBITS, default=defaults.get(CONF_STOPBITS, 1)): vol.In([1, 2])})
        else:
            host = ({'default': defaults[CONF_HOST]} if CONF_HOST in defaults else {})
            fields.update({vol.Required(CONF_HOST, **host): str,
                vol.Required(CONF_TCP_PORT, default=defaults.get(CONF_TCP_PORT, 5000)): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Required(CONF_CONNECT_TIMEOUT, default=defaults.get(CONF_CONNECT_TIMEOUT, 10)): vol.All(vol.Coerce(float), vol.Range(min=1, max=120))})
        freshness = ({'default': defaults[CONF_STALE_AFTER]} if CONF_STALE_AFTER in defaults else {})
        fields[vol.Required(CONF_STALE_AFTER, **freshness)] = vol.All(vol.Coerce(float), vol.Range(min=1, max=86400))
        fields[vol.Optional(CONF_LOCAL_POLLING,default=defaults.get(CONF_LOCAL_POLLING,False))] = bool
        extra_default = {'default': defaults['extended_parameters']} if 'extended_parameters' in defaults else {}
        fields[vol.Optional('extended_parameters', **extra_default)] = bool
        fields[vol.Optional('clock_sync', default=defaults.get('clock_sync', False))] = bool
        return vol.Schema(fields)

    async def _transport_step(self, kind, user_input):
        errors = {}
        if user_input is not None:
            try:
                data = self._schema(kind)(user_input)
                data[CONF_NAME] = data[CONF_NAME].strip()
                if not data[CONF_NAME]: raise ValueError('Name cannot be empty')
                endpoint = CONF_SERIAL_PORT if kind == 'serial' else CONF_HOST
                data[endpoint] = data[endpoint].strip()
                data[CONF_TRANSPORT] = kind
                transport_config(data)
                target = self._entry()
                for entry in self._async_current_entries():
                    if (target is None or entry.entry_id != target.entry_id) and endpoint_key(entry.data) == endpoint_key(data):
                        return self.async_abort(reason='endpoint_configured')
                if target:
                    return self.async_update_reload_and_abort(target, data=data, title=data[CONF_NAME])
                await self.async_set_unique_id(uuid4().hex)
                return self.async_create_entry(title=data[CONF_NAME], data=data)
            except (ValueError, vol.Invalid):
                errors['base'] = 'invalid_config'
        return self.async_show_form(step_id=kind, data_schema=self._schema(kind), errors=errors)

    async def async_step_serial(self, user_input=None):
        return await self._transport_step('serial', user_input)

    async def async_step_tcp(self, user_input=None):
        return await self._transport_step('tcp', user_input)
