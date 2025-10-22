import asyncio

from datetime import date
from datetime import datetime
from enum import StrEnum
from typing import Optional
from typing import Union
from typing import cast

from homeassistant.components.event import EventEntity, EventDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.const import PERCENTAGE
from homeassistant.const import UnitOfTemperature
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from plugp100.new.components.battery_component import BatteryComponent
from plugp100.new.components.humidity_component import HumidityComponent
from plugp100.new.components.report_mode_component import ReportModeComponent
from plugp100.new.components.temperature_component import TemperatureComponent
from plugp100.new.components.trigger_log_component import TriggerLogComponent
from plugp100.new.tapodevice import TapoDevice
from plugp100.responses.hub_childs.s200b_device_state import (
    SingleClickEvent,
    DoubleClickEvent,
    RotationEvent,
)
from plugp100.responses.hub_childs.trigger_log_response import TriggerLogResponse
from plugp100.responses.temperature_unit import TemperatureUnit

from custom_components.tapo.const import DOMAIN
from custom_components.tapo.coordinators import HassTapoDeviceData
from custom_components.tapo.coordinators import TapoDataCoordinator
from custom_components.tapo.entity import CoordinatedTapoEntity

COMPONENT_MAPPING = {
    HumidityComponent: 'HumiditySensor',
    TemperatureComponent: 'TemperatureSensor',
    ReportModeComponent: 'ReportIntervalDiagnostic',
    BatteryComponent: 'BatteryLevelSensor',
    TriggerLogComponent: 'TriggerEvent'
}

class TriggerEventTypes(StrEnum):
    """Available event types reported by the TriggerEvent entity."""

    SINGLE_PRESS = "single_press"
    DOUBLE_PRESS = "double_press"
    ROTATE_CLOCKWISE = "rotate_clockwise"
    ROTATE_ANTICLOCKWISE = "rotate_anticlockwise"

async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    data = cast(HassTapoDeviceData, hass.data[DOMAIN][entry.entry_id])
    for child_coordinator in data.child_coordinators:
        sensors = [
            eval(cls)(child_coordinator, child_coordinator.device)
            for (component, cls) in COMPONENT_MAPPING.items()
            if child_coordinator.device.has_component(component)
        ]
        # temporary workaround to avoid getting battery percentage on not supported devices
        if battery := child_coordinator.device.get_component(BatteryComponent):
            if battery.battery_percentage == -1:
                sensors = list(filter(lambda x: not isinstance(x, BatteryLevelSensor), sensors))

        async_add_entities(sensors, True)


class HumiditySensor(CoordinatedTapoEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator: TapoDataCoordinator,
            device: TapoDevice
    ):
        super().__init__(coordinator, device)
        self._attr_name = "Humidity"

    @property
    def unique_id(self):
        return super().unique_id + "_" + self._attr_name.replace(" ", "_")

    @property
    def device_class(self) -> Optional[str]:
        return SensorDeviceClass.HUMIDITY

    @property
    def state_class(self) -> Optional[str]:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        return PERCENTAGE

    @property
    def native_value(self) -> Union[StateType, date, datetime]:
        if humidity := self.device.get_component(HumidityComponent):
            return humidity.current_humidity
        return None


class TemperatureSensor(CoordinatedTapoEntity, SensorEntity):
    _attr_has_entity_name = True

    _temperature_component: TemperatureComponent

    def __init__(
            self,
            coordinator: TapoDataCoordinator,
            device: TapoDevice
    ):
        super().__init__(coordinator, device)
        self._attr_name = "Temperature"
        self._temperature_component = device.get_component(TemperatureComponent)

    @property
    def unique_id(self):
        return super().unique_id + "_" + self._attr_name.replace(" ", "_")

    @property
    def device_class(self) -> Optional[str]:
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self) -> Optional[str]:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        if self._temperature_component.temperature_unit == TemperatureUnit.CELSIUS:
            return UnitOfTemperature.CELSIUS
        elif self._temperature_component.temperature_unit == TemperatureUnit.FAHRENHEIT:
            return UnitOfTemperature.FAHRENHEIT
        else:
            return None

    @property
    def native_value(self) -> Union[StateType, date, datetime]:
        return self._temperature_component.current_temperature


class BatteryLevelSensor(CoordinatedTapoEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator: TapoDataCoordinator,
            device: TapoDevice
    ):
        super().__init__(coordinator, device)
        self._attr_name = "Battery Percentage"

    @property
    def unique_id(self):
        return super().unique_id + "_" + self._attr_name.replace(" ", "_")

    @property
    def device_class(self) -> Optional[str]:
        return SensorDeviceClass.BATTERY

    @property
    def state_class(self) -> Optional[str]:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        return PERCENTAGE

    @property
    def native_value(self) -> Union[StateType, date, datetime]:
        return self.device.get_component(BatteryComponent).battery_percentage


class ReportIntervalDiagnostic(CoordinatedTapoEntity, SensorEntity):

    def __init__(
            self,
            coordinator: TapoDataCoordinator,
            device: TapoDevice
    ):
        super().__init__(coordinator, device)
        self._attr_name = "Report Interval"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self):
        return super().unique_id + "_" + self._attr_name.replace(" ", "_")

    @property
    def device_class(self) -> Optional[str]:
        return SensorDeviceClass.DURATION

    @property
    def state_class(self) -> Optional[str]:
        return SensorStateClass.TOTAL

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        return UnitOfTime.SECONDS

    @property
    def native_value(self) -> Union[StateType, date, datetime]:
        return self.device.get_component(ReportModeComponent).report_interval_seconds

class TriggerEvent(CoordinatedTapoEntity, EventEntity):
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = [TriggerEventTypes.SINGLE_PRESS, TriggerEventTypes.DOUBLE_PRESS, TriggerEventTypes.ROTATE_CLOCKWISE, TriggerEventTypes.ROTATE_ANTICLOCKWISE]
    _attr_has_entity_name = True
    _task: Optional[asyncio.tasks.Task] = None
    _last_event_id: Optional[int] = None
    _last_event_type: Optional[str] = None
    _last_rotate_factor: Optional[float] = None

    def __init__(
            self,
            coordinator: TapoDataCoordinator,
            device: TapoDevice
    ):
        super().__init__(coordinator, device)
        self._attr_name = "Trigger Event"

    @property
    def unique_id(self):
        return super().unique_id + "_" + self._attr_name.replace(" ", "_")

    async def event_loop(self):
        while True:
            # Request up to N events at a time and process all that are newer than
            # _last_event_id. We iterate oldest->newest to preserve event order.
            # This reduces the chance of missing events that occur between loop
            # iterations.
            BATCH_SIZE = 10
            maybe_response = await self.device.get_component(TriggerLogComponent).get_event_logs(BATCH_SIZE)
            response = maybe_response.get_or_else(TriggerLogResponse(0, 0, []))

            # If we have no last_event_id, skip the newest event on first run to
            # avoid re-reporting historical events. However, if multiple events
            # exist and last_event_id is None, set it to the newest ID so we
            # won't re-emit history.
            if self._last_event_id is None and len(response.events) > 0:
                # Set to the newest event id (last in list) to avoid emitting
                # historical events immediately.
                self._last_event_id = response.events[-1].id
            else:
                # Process all events older->newer and emit those with id > _last_event_id
                # If _last_event_id is None, the above branch set it; here it's safe
                # to assume it is set.
                saw_new = False

                # If there are no events returned but we have a known last_event_id,
                # then nothing changed since last check — set state to idle.
                if len(response.events) == 0:
                    if self._last_event_id is not None:
                        await self._set_idle()
                else:
                    for ev in response.events:
                        # Only handle events strictly newer than the last seen
                        if self._last_event_id is not None and ev.id <= self._last_event_id:
                            continue

                        saw_new = True

                        # Determine event type and optional rotate_factor
                        rotate_factor = None
                        if isinstance(ev, SingleClickEvent):
                            event_type = TriggerEventTypes.SINGLE_PRESS.value
                        elif isinstance(ev, DoubleClickEvent):
                            event_type = TriggerEventTypes.DOUBLE_PRESS.value
                        elif isinstance(ev, RotationEvent) and ev.degrees >= 0:
                            event_type = TriggerEventTypes.ROTATE_CLOCKWISE.value
                            try:
                                rotate_factor = float(ev.degrees) / 360.0
                            except Exception:
                                rotate_factor = None
                        elif isinstance(ev, RotationEvent) and ev.degrees < 0:
                            event_type = TriggerEventTypes.ROTATE_ANTICLOCKWISE.value
                            try:
                                rotate_factor = float(ev.degrees) / 360.0
                            except Exception:
                                rotate_factor = None
                        else:
                            # Unknown event type — skip
                            continue

                        # Emit the event and update the HA state
                        await self._emit_event(event_type, rotate_factor)

                        # Update last seen id to this event
                        self._last_event_id = ev.id

                        # Briefly show an idle state between rapid events so the
                        # frontend can display a short gap. Wait 100ms and set
                        # state to "idle" before continuing to the next event.
                        await self.sleep_then_set_idle(0.1)

                    # If no new events were detected (all IDs <= _last_event_id),
                    # set the state to idle.
                    if not saw_new:
                        await self._set_idle()

            await asyncio.sleep(0.5)

    async def async_added_to_hass(self) -> None:
        self._task = asyncio.create_task(self.event_loop())

    async def _emit_event(self, event_type: str, rotate_factor: Optional[float] = None) -> None:
        """Emit an event and update the entity state/attributes.

        Sets _last_event_type and _last_rotate_factor, triggers the HA event,
        and writes the HA state.
        """
        self._last_event_type = event_type
        self._last_rotate_factor = rotate_factor
        # Emit the event on the entity
        self._trigger_event(self._last_event_type)
        # Write state so UI reflects the event and attributes
        self.async_write_ha_state()

    async def _set_idle(self) -> None:
        """Set the entity state to 'idle' and clear rotate factor if needed."""
        if self._last_event_type != "idle":
            self._last_event_type = "idle"
            self._last_rotate_factor = None
            self.async_write_ha_state()

    async def sleep_then_set_idle(self, seconds: float) -> None:
        """Set the entity to idle, write state, then sleep for `seconds`."""
        await asyncio.sleep(seconds)
        await self._set_idle()

    @property
    def state(self) -> Optional[str]:
        """Return the last event type string as the entity state.

        Falls back to the default EventEntity state (timestamp) if no event type
        has been recorded yet.
        """
        if self._last_event_type is not None:
            return self._last_event_type
        return super().state

    @property
    def extra_state_attributes(self) -> dict:
        """Return any extra attributes for the entity state.

        We expose `rotate_factor` when available (degrees / 360).
        """
        # Always expose the rotate_factor attribute (value may be None). This
        # ensures Home Assistant shows the attribute in the UI even when no
        # rotation event has recently been recorded.
        return {"rotate_factor": self._last_rotate_factor}

    async def async_will_remove_from_hass(self) -> None:
        self._task.cancel()