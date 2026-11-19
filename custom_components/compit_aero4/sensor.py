"""Home Assistant measurement and setting sensors."""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfRatio, UnitOfTemperature, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers import entity_registry as er
from .entity import Aero4Entity
from .c14.parameters import PARAMETERS
from .c14.protocol import AIR_QUALITY_FRAME_KEY
from .const import DOMAIN

AIR_QUALITY_SENSORS = (
    SensorEntityDescription(key='air_co2', translation_key='air_co2',
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0),
    *(SensorEntityDescription(key=key, translation_key=key,
        native_unit_of_measurement=PERCENTAGE, icon='mdi:blur',
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0)
      for key in ('air_pm25_percent', 'air_pm10_percent')),
)

SENSORS = (
    SensorEntityDescription(key='room_humidity', translation_key='room_humidity',
        device_class=SensorDeviceClass.HUMIDITY, native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1),
    *(SensorEntityDescription(key=key, translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE, native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1)
      for key in ('outdoor_temperature', 'supply_temperature', 'room_temperature',
                  'exhaust_temperature', 'extract_temperature')),
    SensorEntityDescription(key='room_temperature_setpoint', translation_key='room_temperature_setpoint',
        device_class=SensorDeviceClass.TEMPERATURE, native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1),
    *(SensorEntityDescription(key=key, translation_key=key, native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC)
      for key in ('fan_a_percent', 'fan_b_percent', 'ao3_percent')),
    SensorEntityDescription(key='ventilation_requested', translation_key='ventilation_requested',
        device_class=SensorDeviceClass.ENUM, options=['stopped', 'B1', 'B2', 'B3']),
    SensorEntityDescription(key='ventilation_mode_requested', translation_key='ventilation_mode_requested',
        device_class=SensorDeviceClass.ENUM, options=['stopped', 'B1', 'B2', 'B3', 'holiday_schedule', 'schedule']),
    SensorEntityDescription(key='bypass_requested', translation_key='bypass_requested',
        device_class=SensorDeviceClass.ENUM, options=['OFF', 'AUTO', 'ON']),
    *(SensorEntityDescription(key=key, translation_key=key, device_class=SensorDeviceClass.ENUM,
        options=options, entity_category=EntityCategory.DIAGNOSTIC, entity_registry_enabled_default=False)
      for key, options in (('bypass_readback', ['OFF', 'AUTO', 'ON']),
                           ('ventilation_mode_readback', ['stopped', 'B1', 'B2', 'B3', 'holiday_schedule', 'schedule']))),
)


async def async_setup_entry(hass, entry, async_add_entities):
    
    
    registry = er.async_get(hass)
    added_air_quality = set()

    @callback
    def discover_air_quality():
        entities = []
        for description in AIR_QUALITY_SENSORS:
            key = description.key
            if key in added_air_quality:
                continue
            info = entry.runtime_data.data['fields'][key]
            registered = registry.async_get_entity_id('sensor', DOMAIN, f'{entry.entry_id}_{key}')
            if registered or info.get('source_key') == AIR_QUALITY_FRAME_KEY:
                added_air_quality.add(key)
                entities.append(Aero4AirQualitySensor(entry.runtime_data, description))
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(entry.runtime_data.async_add_listener(discover_air_quality))
    discover_air_quality()
    if entry.data.get('extended_parameters', False):
        async_add_entities([Aero4FilterRemainingSensor(entry.runtime_data, SensorEntityDescription(
            key='filter_days_remaining', translation_key='filter_days_remaining',
            native_unit_of_measurement=UnitOfTime.DAYS, suggested_display_precision=0,
            icon='mdi:air-filter'))])
        async_add_entities([Aero4Sensor(entry.runtime_data, SensorEntityDescription(
            key='fan_runon_duration', translation_key='fan_runon_duration',
            device_class=SensorDeviceClass.DURATION, native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_display_precision=0, entity_category=EntityCategory.DIAGNOSTIC))])
        async_add_entities([Aero4ParameterScanSensor(entry.runtime_data, SensorEntityDescription(
            key='parameter_scan_progress', translation_key='parameter_scan_progress',
            native_unit_of_measurement=PERCENTAGE, suggested_display_precision=0,
            entity_category=EntityCategory.DIAGNOSTIC, icon='mdi:database'))])
        async_add_entities([Aero4ParameterCommandSensor(entry.runtime_data, SensorEntityDescription(
            key='parameter_command_status', translation_key='parameter_command_status',
            device_class=SensorDeviceClass.ENUM, options=['idle', 'queued', 'waiting', 'succeeded', 'failed'],
            entity_category=EntityCategory.DIAGNOSTIC))])
        async_add_entities([Aero4ScheduleStatusSensor(entry.runtime_data, SensorEntityDescription(
            key='schedule_command_status', translation_key='schedule_command_status',
            device_class=SensorDeviceClass.ENUM, options=['idle', 'waiting', 'succeeded', 'failed'],
            entity_category=EntityCategory.DIAGNOSTIC))])
    async_add_entities([Aero4ParameterReadbackSensor(entry.runtime_data, SensorEntityDescription(
        key=p.field, translation_key=p.key, native_unit_of_measurement=p.unit,
        device_class=(SensorDeviceClass.TEMPERATURE if p.unit == '°C' and not p.temperature_delta else
                      SensorDeviceClass.ENUM if p.options and p.category == 'setting' else None),
        options=([('on' if value else 'off') if type(value) is bool else value for _, value in p.options]
                 if p.options and p.category == 'setting' else None),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=p.category == 'setting' and not p.writable,
        icon='mdi:clock-outline' if p.category == 'schedule' else 'mdi:thermometer' if p.unit == '°C' else 'mdi:tune'))
        for p in PARAMETERS.values() if entry.data.get('extended_parameters', False)])
    async_add_entities([*(Aero4Sensor(entry.runtime_data, description) for description in SENSORS),
        Aero4PollingSensor(entry.runtime_data,SensorEntityDescription(key='local_polling_status',
            translation_key='local_polling_status',device_class=SensorDeviceClass.ENUM,
            options=['disabled','stopped','learning','ready','polling','blocked','fault'],
            entity_category=EntityCategory.DIAGNOSTIC))])
    async_add_entities([Aero4CommandSensor(entry.runtime_data,SensorEntityDescription(
        key=key,translation_key=key,
        device_class=SensorDeviceClass.ENUM,options=['idle','queued','waiting','succeeded','failed'],
        entity_category=EntityCategory.DIAGNOSTIC)) for key in ('bypass_command_status','boost_command_status','ventilation_command_status')])


class Aero4Sensor(Aero4Entity, SensorEntity):
    @property
    def native_value(self):
        return self.coordinator.data['fields'][self.entity_description.key]['value']


class Aero4AirQualitySensor(Aero4Sensor):
    """Optional air-quality measurements."""

    @property
    def available(self):
        return (super().available
                and self.coordinator.data['fields'][self.entity_description.key]['status'] == 'known')


class Aero4ParameterReadbackSensor(Aero4Sensor):
    """Stored values remain observable even when local control is unavailable."""

    @property
    def native_value(self):
        value = super().native_value
        return ('on' if value else 'off') if type(value) is bool else value


class Aero4FilterRemainingSensor(Aero4Entity, SensorEntity):
    """Nano's supported interval minus elapsed-days calculation; never a reset."""

    @property
    def available(self):
        fields = self.coordinator.data['fields']
        return (super().available and self.coordinator.data['transport']['connected']
                and all(fields[key]['status'] == 'known' for key in (
                    'parameter_filter_reminder_period', 'parameter_filter_elapsed_days'))
                and fields['parameter_filter_reminder_period']['value'] > 0)

    @property
    def native_value(self):
        if not self.available:
            return None
        fields = self.coordinator.data['fields']
        return (fields['parameter_filter_reminder_period']['value']
                - fields['parameter_filter_elapsed_days']['value'])


class Aero4PollingSensor(Aero4Entity, SensorEntity):
    @property
    def native_value(self):
        return self.coordinator.data['polling']['status']


class Aero4CommandSensor(Aero4Entity, SensorEntity):
    @property
    def native_value(self):
        command=self.coordinator.data['command']
        return command['status'] if command['key']==self.entity_description.key.removesuffix('_command_status') else 'idle'

    @property
    def extra_state_attributes(self):
        command = self.coordinator.data['command']
        return {'requested':command['requested'] if command['key']==self.entity_description.key.removesuffix('_command_status') else None}


class Aero4ScheduleStatusSensor(Aero4Entity, SensorEntity):
    @property
    def native_value(self):
        return self.coordinator.data['schedule_operation']['status']

    @property
    def extra_state_attributes(self):
        return {key: value for key, value in self.coordinator.data['schedule_operation'].items() if key != 'status'}


class Aero4ParameterCommandSensor(Aero4Entity, SensorEntity):
    @property
    def native_value(self):
        return self.coordinator.data['command']['status'] if self._matches else 'idle'

    @property
    def _matches(self):
        command = self.coordinator.data['command']
        return command['key'] in ('parameter_refresh','filter_reset') or command['key'] in PARAMETERS and command['key'] not in ('bypass', 'boost')

    @property
    def extra_state_attributes(self):
        command = self.coordinator.data['command']
        return {key: command.get(key) if self._matches else None for key in ('key', 'requested', 'error', 'confirmation', 'kind', 'target')}


class Aero4ParameterScanSensor(Aero4Entity, SensorEntity):
    @property
    def available(self):
        return super().available and self.coordinator.data['transport']['connected']

    @property
    def native_value(self):
        scan = self.coordinator.data['parameter_scan']
        if not scan['total']:
            return None
        return 100 if scan['received'] == scan['total'] else min(99, round(100 * scan['received'] / scan['total']))

    @property
    def extra_state_attributes(self):
        return {**self.coordinator.data['parameter_scan'],
                'batch_count': self.coordinator.data['polling']['batch_count']}
