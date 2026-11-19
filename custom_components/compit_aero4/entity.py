"""Stable device identity and per-field availability."""
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .c14.parameters import PARAMETERS


class Aero4Entity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f'{coordinator.entry.entry_id}_{description.key}'
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.entry.entry_id)},
            model='AERO 4', name=coordinator.entry.title)

    @property
    def available(self):
        if not super().available:
            return False
        info = self.coordinator.data.get('fields', {}).get(self.entity_description.key)
        return info is None or (self.coordinator.data['transport']['connected'] and info['status'] != 'unavailable')

    @property
    def extra_state_attributes(self):
        info = self.coordinator.data.get('fields', {}).get(self.entity_description.key)
        if info is None:
            return None
        
        
        attributes = {key: info[key] for key in ('source_key', 'value_status') if key in info}
        if self.entity_description.key == 'parameter_ventilation_enabled':
            attributes['control_queue'] = self.coordinator.data.get('control_queue', {})
        parameter = PARAMETERS.get(self.entity_description.key.removeprefix('parameter_'))
        if parameter is not None and parameter.disabled_at is not None:
            attributes.update(disabled_at_native_value=parameter.disabled_at,
                disabled_at_native_unit=parameter.unit,
                function_enabled=info['value'] != parameter.disabled_at if info['status']=='known' else None)
        return attributes
