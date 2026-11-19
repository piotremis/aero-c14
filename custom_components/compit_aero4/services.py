"""Admin actions for captures and the native eight-day Nano schedule."""
import voluptuous as vol
import asyncio
import math
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.service import async_register_admin_service
from .const import DOMAIN
from .c14.recording import CaptureQuotaExceeded
from .c14.commands import CommandError
from .c14.schedule import schedule_snapshot, period_keys
from .c14.parameters import SCHEDULE_DAYS, PARAMETERS


def _period(value):
    if type(value) not in (int, float) or not 1 <= value <= 3 or not math.isfinite(value) or value != int(value):
        raise vol.Invalid('Period must be an integer from 1 to 3')
    return int(value)


def async_register_services(hass):
    lock=asyncio.Lock()
    def coordinator(call):
        entry_id = call.data.get('entry_id')
        entries = [entry for entry in hass.config_entries.async_entries(DOMAIN)
                   if getattr(entry,'runtime_data',None) is not None and
                   (entry_id is None or entry.entry_id==entry_id)]
        if len(entries)!=1:
            raise ServiceValidationError(translation_domain=DOMAIN,translation_key='capture_choose_entry')
        return entries[0].runtime_data

    async def start(call):
        try:
            async with lock:
                if any(getattr(entry,'runtime_data',None) is not None and
                       entry.runtime_data.capture is not None and entry.runtime_data.capture.running
                       for entry in hass.config_entries.async_entries(DOMAIN)):
                    raise RuntimeError('Capture already running')
                return await coordinator(call).async_start_capture(call.data['duration'])
        except CaptureQuotaExceeded as error:
            raise ServiceValidationError(translation_domain=DOMAIN,translation_key='capture_quota_reached') from error
        except RuntimeError as error:
            raise ServiceValidationError(translation_domain=DOMAIN,translation_key='capture_unavailable') from error
        except (OSError,TimeoutError) as error:
            raise ServiceValidationError(translation_domain=DOMAIN,translation_key='capture_io_error') from error

    async def stop(call):
        try:
            return await coordinator(call).async_stop_capture()
        except (OSError,TimeoutError) as error:
            raise ServiceValidationError(translation_domain=DOMAIN,translation_key='capture_io_error') from error

    async def get_schedule(call):
        co = coordinator(call)
        if day := call.data.get('refresh_day'):
            try:
                keys = [key for period in range(1, 4) for key in period_keys(day, period)]
                await co.receiver.async_refresh_parameters(keys)
            except CommandError as error:
                key = {'busy': 'command_busy', 'control_unavailable': 'control_unavailable'}.get(str(error), 'command_not_confirmed')
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key=key) from error
        return {'days': schedule_snapshot(co.data['fields']), 'minutes_per_unit': 15}

    async def refresh_parameters(call):
        try:
            return {'fields': await coordinator(call).receiver.async_refresh_parameters(call.data['keys'])}
        except CommandError as error:
            key = {'busy': 'command_busy', 'control_unavailable': 'control_unavailable'}.get(str(error), 'command_not_confirmed')
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key=key) from error

    async def set_schedule(call):
        try:
            return await coordinator(call).receiver.async_set_schedule_period(
                call.data['day'], call.data['period'], call.data['start'], call.data['end'])
        except ValueError as error:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key='invalid_schedule') from error
        except CommandError as error:
            key = {'busy': 'command_busy', 'control_unavailable': 'control_unavailable'}.get(
                str(error), 'schedule_not_confirmed')
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key=key) from error

    async def user_control(call):
        from homeassistant.helpers import entity_registry as er
        from homeassistant.auth.permissions.const import POLICY_CONTROL
        entity_id = call.data['entity_id']
        registry = er.async_get(hass)
        entity = registry.async_get(entity_id)
        if entity is None or entity.platform != DOMAIN:
            raise ServiceValidationError('Choose an AERO C14 control entity')
        
        if call.context.user_id:
            user = await hass.auth.async_get_user(call.context.user_id)
            controls = [e.entity_id for e in registry.entities.values()
                        if e.config_entry_id == entity.config_entry_id and e.domain in ('switch','select','number')]
            if user is None or any(not user.permissions.check_entity(e, POLICY_CONTROL) for e in controls):
                raise ServiceValidationError('Control permission required')
        entry = hass.config_entries.async_get_entry(entity.config_entry_id)
        if entry is None or getattr(entry, 'runtime_data', None) is None:
            raise ServiceValidationError('Device unavailable')
        try:
            await entry.runtime_data.receiver.async_user_control(call.data['action'], call.data['value'])
        except ValueError as error:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key='invalid_parameter_value') from error
        except CommandError as error:
            key = {'busy':'command_busy','control_unavailable':'control_unavailable'}.get(str(error),'command_not_confirmed')
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key=key) from error

    hass.services.async_register(DOMAIN, 'user_control', user_control,
        schema=vol.Schema({vol.Required('entity_id'):str,
            vol.Required('action'):vol.In(('mode','gear','boost')), vol.Required('value'):str}))

    base = {vol.Optional('entry_id'):str}
    async_register_admin_service(hass,DOMAIN,'start_capture',start,
        schema=vol.Schema({**base,vol.Optional('duration',default=120):vol.All(vol.Coerce(int),vol.Range(min=1,max=900))}),
        supports_response=SupportsResponse.OPTIONAL)
    async_register_admin_service(hass,DOMAIN,'stop_capture',stop,
        schema=vol.Schema(base),supports_response=SupportsResponse.OPTIONAL)
    async_register_admin_service(hass,DOMAIN,'get_schedule',get_schedule,
        schema=vol.Schema({**base, vol.Optional('refresh_day'): vol.In(SCHEDULE_DAYS)}), supports_response=SupportsResponse.ONLY)
    async_register_admin_service(hass,DOMAIN,'refresh_parameters',refresh_parameters,
        schema=vol.Schema({**base, vol.Required('keys'): vol.All(list, [vol.In(PARAMETERS)], vol.Length(min=1,max=len(PARAMETERS)))}),
        supports_response=SupportsResponse.OPTIONAL)
    async_register_admin_service(hass,DOMAIN,'set_schedule_period',set_schedule,
        schema=vol.Schema({**base, vol.Required('day'): vol.In(SCHEDULE_DAYS),
            vol.Required('period'): _period,
            vol.Required('start'): str, vol.Required('end'): str}),
        supports_response=SupportsResponse.OPTIONAL)
