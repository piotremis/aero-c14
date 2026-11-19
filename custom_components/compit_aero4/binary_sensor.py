"""Reported states and distinct link/bus/AERO connectivity indicators."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.helpers.entity import EntityCategory
from .entity import Aero4Entity
from .c14.parameters import PARAMETERS

BINARY_SENSORS = (
    BinarySensorEntityDescription(key='filter_maintenance_due',translation_key='filter_maintenance_due',
        device_class=BinarySensorDeviceClass.PROBLEM),
    *(BinarySensorEntityDescription(key=key, translation_key=key)
      for key in ('boost_requested', 'boost_active')),
    BinarySensorEntityDescription(key='bypass_reported_open', translation_key='bypass_reported_open',
        device_class=BinarySensorDeviceClass.OPENING),
    BinarySensorEntityDescription(key='boost_readback', translation_key='boost_readback',
        entity_category=EntityCategory.DIAGNOSTIC, entity_registry_enabled_default=False),
    *(BinarySensorEntityDescription(key=key, translation_key=key,
        device_class=BinarySensorDeviceClass.CONNECTIVITY, entity_category=EntityCategory.DIAGNOSTIC)
      for key in ('transport_connected', 'bus_online', 'aero_online')),
)


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get('extended_parameters', False):
        async_add_entities([Aero4BinarySensor(entry.runtime_data, BinarySensorEntityDescription(
            key='gwc_reported_active', translation_key='gwc_reported_active', icon='mdi:pipe-valve'))])
    if entry.data.get('extended_parameters', False):
        async_add_entities(Aero4ThresholdEnabledSensor(entry.runtime_data, BinarySensorEntityDescription(
            key=p.field+'_threshold_enabled', translation_key=p.key+'_threshold_enabled',
            entity_category=EntityCategory.DIAGNOSTIC, icon='mdi:thermometer-check'))
            for p in PARAMETERS.values() if p.disabled_at is not None)
    async_add_entities(Aero4BinarySensor(entry.runtime_data, description) for description in BINARY_SENSORS)


class Aero4BinarySensor(Aero4Entity, BinarySensorEntity):
    @property
    def is_on(self):
        key = self.entity_description.key
        if key == 'transport_connected':
            return self.coordinator.data['transport']['connected']
        if key in ('bus_online', 'aero_online'):
            return self.coordinator.data[key]
        return self.coordinator.data['fields'][key]['value']


class Aero4ThresholdEnabledSensor(Aero4Entity, BinarySensorEntity):
    @property
    def parameter(self):
        key=self.entity_description.key.removeprefix('parameter_').removesuffix('_threshold_enabled')
        return PARAMETERS[key]

    @property
    def info(self):
        return self.coordinator.data['fields'][self.parameter.field]

    @property
    def available(self):
        return super().available and self.coordinator.data['transport']['connected'] and self.info['status']=='known'

    @property
    def is_on(self):
        if self.info['status']!='known':
            return None
        return self.info['value'] != self.parameter.disabled_at
