"""amshan platform."""
from __future__ import annotations

from asyncio import Queue
from datetime import datetime
import logging
from math import floor
from typing import Callable, ClassVar, Iterable, NamedTuple, cast

from amshan.autodecoder import AutoDecoder
import amshan.obis_map as obis_map
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_POTENTIAL_VOLT,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import DeviceInfo, Entity, EntityCategory
from homeassistant.helpers.typing import HomeAssistantType

from . import MeterInfo
from .const import (
    CONF_OPTIONS_SCALE_FACTOR,
    DOMAIN,
    ENTRY_DATA_MEASURE_QUEUE,
    ICON_COUNTER,
    ICON_CURRENT,
    ICON_POWER_EXPORT,
    ICON_POWER_IMPORT,
    ICON_VOLTAGE,
    UNIT_KILO_VOLT_AMPERE_REACTIVE,
    UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


class EntitySetup(NamedTuple):
    """Entity setup."""

    """Use custom configured scaling."""
    use_configured_scaling: bool

    """Scaling, if any, to be done one the measured value to be in correct unit."""
    scale: float | None

    """Specify a number to round the measure source value to that number of decimals."""
    decimals: int | None

    sensor_entity_description: SensorEntityDescription


async def async_setup_entry(
    hass: HomeAssistantType,
    config_entry: ConfigEntry,
    async_add_entities: Callable[[list[Entity], bool], None],
):
    """Add hantest sensor platform from a config_entry."""
    measure_queue = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_MEASURE_QUEUE]
    processor: MeterMeasureProcessor = MeterMeasureProcessor(
        hass, config_entry, async_add_entities, measure_queue
    )
    hass.loop.create_task(processor.async_process_measures_loop())


class NorhanEntity(SensorEntity):
    """Representation of a Norhan sensor."""

    ENTITY_SETUPS: ClassVar[dict[str, EntitySetup]] = {
        obis_map.NEK_HAN_FIELD_METER_ID: EntitySetup(
            False,
            None,
            None,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_METER_ID,
                entity_category=EntityCategory.DIAGNOSTIC,
                device_class=None,
                native_unit_of_measurement=None,
                state_class=None,
                name="Meter ID",
            ),
        ),
        obis_map.NEK_HAN_FIELD_METER_MANUFACTURER: EntitySetup(
            False,
            None,
            None,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_METER_MANUFACTURER,
                entity_category=EntityCategory.DIAGNOSTIC,
                device_class=None,
                native_unit_of_measurement=None,
                state_class=None,
                icon=None,
                name="Meter manufacturer",
            ),
        ),
        obis_map.NEK_HAN_FIELD_METER_TYPE: EntitySetup(
            False,
            None,
            None,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_METER_TYPE,
                entity_category=EntityCategory.DIAGNOSTIC,
                device_class=None,
                native_unit_of_measurement=None,
                state_class=None,
                icon=None,
                name="Meter type",
            ),
        ),
        obis_map.NEK_HAN_FIELD_OBIS_LIST_VER_ID: EntitySetup(
            False,
            None,
            None,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_OBIS_LIST_VER_ID,
                entity_category=EntityCategory.DIAGNOSTIC,
                device_class=None,
                native_unit_of_measurement=None,
                state_class=None,
                icon=None,
                name="OBIS List version identifier",
            ),
        ),
        obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT: EntitySetup(
            True,
            None,
            0,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT,
                entity_category=None,
                device_class=SensorDeviceClass.POWER,
                native_unit_of_measurement=POWER_WATT,
                state_class=SensorStateClass.MEASUREMENT,
                icon=ICON_POWER_IMPORT,
                name="Active power import (Q1+Q4)",
            ),
        ),
        obis_map.NEK_HAN_FIELD_ACTIVE_POWER_EXPORT: EntitySetup(
            True,
            None,
            0,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_ACTIVE_POWER_EXPORT,
                entity_category=None,
                device_class=SensorDeviceClass.POWER,
                native_unit_of_measurement=POWER_WATT,
                state_class=SensorStateClass.MEASUREMENT,
                icon=ICON_POWER_EXPORT,
                name="Active power export (Q2+Q3)",
            ),
        ),
        obis_map.NEK_HAN_FIELD_REACTIVE_POWER_IMPORT: EntitySetup(
            True,
            0.001,
            3,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_REACTIVE_POWER_IMPORT,
                entity_category=None,
                device_class=None,
                native_unit_of_measurement=UNIT_KILO_VOLT_AMPERE_REACTIVE,
                state_class=SensorStateClass.MEASUREMENT,
                icon=ICON_POWER_IMPORT,
                name="Reactive power import (Q1+Q2)",
            ),
        ),
        obis_map.NEK_HAN_FIELD_REACTIVE_POWER_EXPORT: EntitySetup(
            True,
            0.001,
            3,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_REACTIVE_POWER_EXPORT,
                entity_category=None,
                device_class=None,
                native_unit_of_measurement=UNIT_KILO_VOLT_AMPERE_REACTIVE,
                state_class=SensorStateClass.MEASUREMENT,
                icon=ICON_POWER_EXPORT,
                name="Reactive power export (Q3+Q4)",
            ),
        ),
        obis_map.NEK_HAN_FIELD_CURRENT_L1: EntitySetup(
            True,
            None,
            3,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_CURRENT_L1,
                entity_category=None,
                device_class=SensorDeviceClass.CURRENT,
                native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
                state_class=SensorStateClass.MEASUREMENT,
                icon=ICON_CURRENT,
                name="IL1 Current phase L1",
            ),
        ),
        obis_map.NEK_HAN_FIELD_CURRENT_L2: EntitySetup(
            True,
            None,
            3,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_CURRENT_L2,
                entity_category=None,
                device_class=SensorDeviceClass.CURRENT,
                native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
                state_class=SensorStateClass.MEASUREMENT,
                name="IL2 Current phase L2",
            ),
        ),
        obis_map.NEK_HAN_FIELD_CURRENT_L3: EntitySetup(
            True,
            None,
            3,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_CURRENT_L3,
                entity_category=None,
                device_class=SensorDeviceClass.CURRENT,
                native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
                state_class=SensorStateClass.MEASUREMENT,
                name="IL3 Current phase L3",
            ),
        ),
        obis_map.NEK_HAN_FIELD_VOLTAGE_L1: EntitySetup(
            False,
            None,
            1,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_VOLTAGE_L1,
                entity_category=None,
                device_class=SensorDeviceClass.VOLTAGE,
                native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
                state_class=SensorStateClass.MEASUREMENT,
                icon=ICON_VOLTAGE,
                name="UL1 Phase voltage",
            ),
        ),
        obis_map.NEK_HAN_FIELD_VOLTAGE_L2: EntitySetup(
            False,
            None,
            1,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_VOLTAGE_L2,
                entity_category=None,
                device_class=SensorDeviceClass.VOLTAGE,
                native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
                state_class=SensorStateClass.MEASUREMENT,
                icon=ICON_VOLTAGE,
                name="UL2 Phase voltage",
            ),
        ),
        obis_map.NEK_HAN_FIELD_VOLTAGE_L3: EntitySetup(
            False,
            None,
            1,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_VOLTAGE_L3,
                entity_category=None,
                device_class=SensorDeviceClass.VOLTAGE,
                native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
                state_class=SensorStateClass.MEASUREMENT,
                icon=ICON_VOLTAGE,
                name="UL3 Phase voltage",
            ),
        ),
        obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT_HOUR: EntitySetup(
            True,
            0.001,
            2,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT_HOUR,
                entity_category=None,
                device_class=SensorDeviceClass.ENERGY,
                native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
                state_class=SensorStateClass.TOTAL_INCREASING,
                icon=ICON_COUNTER,
                name="Cumulative hourly active import energy (A+) (Q1+Q4)",
            ),
        ),
        obis_map.NEK_HAN_FIELD_ACTIVE_POWER_EXPORT_HOUR: EntitySetup(
            True,
            0.001,
            2,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_ACTIVE_POWER_EXPORT_HOUR,
                entity_category=None,
                device_class=SensorDeviceClass.ENERGY,
                native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
                state_class=SensorStateClass.TOTAL_INCREASING,
                icon=ICON_COUNTER,
                name="Cumulative hourly active export energy (A-) (Q2+Q3)",
            ),
        ),
        obis_map.NEK_HAN_FIELD_REACTIVE_POWER_IMPORT_HOUR: EntitySetup(
            True,
            0.001,
            2,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_REACTIVE_POWER_IMPORT_HOUR,
                entity_category=None,
                device_class=None,
                native_unit_of_measurement=UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS,
                state_class=SensorStateClass.TOTAL_INCREASING,
                icon=ICON_COUNTER,
                name="Cumulative hourly reactive import energy (R+) (Q1+Q2)",
            ),
        ),
        obis_map.NEK_HAN_FIELD_REACTIVE_POWER_EXPORT_HOUR: EntitySetup(
            True,
            0.001,
            2,
            SensorEntityDescription(
                key=obis_map.NEK_HAN_FIELD_REACTIVE_POWER_EXPORT_HOUR,
                entity_category=None,
                device_class=None,
                native_unit_of_measurement=UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS,
                state_class=SensorStateClass.TOTAL_INCREASING,
                icon=ICON_COUNTER,
                name="Cumulative hourly reactive import energy (R-) (Q3+Q4)",
            ),
        ),
    }

    def __init__(
        self,
        measure_id: str,
        measure_data: dict[str, str | int | float | datetime],
        new_measure_signal_name: str,
        scale_factor: float,
    ) -> None:
        """Initialize NorhanEntity class."""
        if measure_id is None:
            raise TypeError("measure_id is required")
        if measure_data is None:
            raise TypeError("measure_data is required")
        if obis_map.NEK_HAN_FIELD_METER_ID not in measure_data:
            raise ValueError(
                f"Expected element {obis_map.NEK_HAN_FIELD_METER_ID} not in measure_data."
            )
        if new_measure_signal_name is None:
            raise TypeError("new_measure_signal_name is required")

        self._measure_data = measure_data
        self._entity_setup = NorhanEntity.ENTITY_SETUPS[measure_id]
        self.entity_description = self._entity_setup.sensor_entity_description
        self._new_measure_signal_name = new_measure_signal_name
        self._async_remove_dispatcher: Callable[[], None] | None = None
        self._meter_info: MeterInfo = MeterInfo.from_measure_data(measure_data)
        self._scale_factor = (
            int(scale_factor) if scale_factor == floor(scale_factor) else scale_factor
        )

    @staticmethod
    def is_measure_id_supported(measure_id: str) -> bool:
        """Check if an entity can be created for measure id."""
        return measure_id in NorhanEntity.ENTITY_SETUPS

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        def on_new_measure(
            measure_data: dict[str, str | int | float | datetime]
        ) -> None:
            if self.measure_id in measure_data:
                self._measure_data = measure_data
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug(
                        "Update sensor %s with state %s",
                        self.unique_id,
                        self.state,
                    )
                self.async_write_ha_state()

        # subscribe to update events for this meter
        self._async_remove_dispatcher = async_dispatcher_connect(
            cast(HomeAssistantType, self.hass),
            self._new_measure_signal_name,
            on_new_measure,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._async_remove_dispatcher:
            self._async_remove_dispatcher()

    @property
    def measure_id(self) -> str:
        """Return the measure_id handled by this entity."""
        return self.entity_description.key

    @property
    def should_poll(self) -> bool:
        """Return False since updates are pushed from this sensor."""
        return False

    @property
    def unique_id(self) -> str | None:
        """Return the unique id."""
        return f"{self._meter_info.manufacturer}-{self._meter_info.meter_id}-{self.measure_id}"

    @property
    def native_value(self) -> None | str | int | float:
        """Return the native value of the entity."""
        measure = self._measure_data.get(self.measure_id)

        if measure is None:
            return None

        if isinstance(measure, str):
            return measure

        if isinstance(measure, datetime):
            return measure.isoformat()

        if self._entity_setup.scale is not None:
            measure = measure * self._entity_setup.scale

        if self._entity_setup.use_configured_scaling:
            measure = measure * self._scale_factor

        if self._entity_setup.decimals is not None:
            measure = (
                round(measure)
                if self._entity_setup.decimals == 0
                else round(measure, self._entity_setup.decimals)
            )

        return measure

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        return DeviceInfo(
            name="HAN port",
            identifiers={(DOMAIN, self._meter_info.unique_id)},
            manufacturer=self._meter_info.manufacturer,
            model=self._meter_info.type,
            sw_version=self._meter_info.list_version_id,
        )


class MeterMeasureProcessor:
    """Process meter measures from queue and setup/update entities."""

    def __init__(
        self,
        hass: HomeAssistantType,
        config_entry: ConfigEntry,
        async_add_entities: Callable[[list[Entity], bool], None],
        measure_queue: Queue[bytes],
    ) -> None:
        """Initialize MeterMeasureProcessor class."""
        self._hass = hass
        self._async_add_entities = async_add_entities
        self._measure_queue = measure_queue
        self._decoder: AutoDecoder = AutoDecoder()
        self._known_measures: set[str] = set()
        self._new_measure_signal_name: str | None = None
        self._scale_factor = float(
            config_entry.options.get(CONF_OPTIONS_SCALE_FACTOR, 1)
        )

    async def async_process_measures_loop(self) -> None:
        """Start the processing loop. The method exits when None is received from queue."""
        while True:
            try:
                measure_data = await self._async_decode_next_valid_frame()
                if not measure_data:
                    _LOGGER.debug("Received stop signal. Exit processing.")
                    return

                _LOGGER.debug("Received meter measures: %s", measure_data)
                self._update_entities(measure_data)
            except Exception as ex:
                _LOGGER.exception("Error processing meter readings: %s", ex)
                raise

    async def _async_decode_next_valid_frame(
        self,
    ) -> dict[str, str | int | float | datetime]:
        while True:
            measure_frame_content = await self._measure_queue.get()
            if not measure_frame_content:
                # stop signal (empty bytes) reveived
                return dict()

            decoded_measure = self._decoder.decode_frame_content(measure_frame_content)
            if decoded_measure:
                _LOGGER.debug("Decoded measure frame: %s", decoded_measure)
                return decoded_measure

            _LOGGER.warning("Could not decode frame: %s", measure_frame_content.hex())

    def _update_entities(
        self, measure_data: dict[str, str | int | float | datetime]
    ) -> None:
        self._ensure_entities_are_created(measure_data)

        # signal all entities to update with new measure data
        if self._known_measures:
            async_dispatcher_send(
                self._hass, self._new_measure_signal_name, measure_data
            )

    def _ensure_entities_are_created(
        self, measure_data: dict[str, str | int | float | datetime]
    ) -> None:
        # meter_id is required to register entities (required for unique_id).
        meter_id = measure_data.get(obis_map.NEK_HAN_FIELD_METER_ID)
        if meter_id:
            missing_measures = measure_data.keys() - self._known_measures

            if missing_measures:

                # Add hourly sensors before measurement is available to avoid long delay
                if (
                    obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT_HOUR
                    not in self._known_measures
                ):
                    missing_measures.update(
                        [
                            obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT_HOUR,
                            obis_map.NEK_HAN_FIELD_ACTIVE_POWER_EXPORT_HOUR,
                            obis_map.NEK_HAN_FIELD_REACTIVE_POWER_IMPORT_HOUR,
                            obis_map.NEK_HAN_FIELD_REACTIVE_POWER_EXPORT_HOUR,
                        ]
                    )

                new_enitities = self._create_entities(
                    missing_measures, str(meter_id), measure_data
                )
                if new_enitities:
                    self._add_entities(new_enitities)

    def _add_entities(self, entities: list[NorhanEntity]):
        new_measures = [x.measure_id for x in entities]
        self._known_measures.update(new_measures)
        _LOGGER.debug(
            "Register new entities for measures: %s",
            new_measures,
        )
        self._async_add_entities(list(entities), True)

    def _create_entities(
        self,
        new_measures: Iterable[str],
        meter_id: str,
        measure_data: dict[str, str | int | float | datetime],
    ) -> list[NorhanEntity]:
        new_enitities: list[NorhanEntity] = []
        for measure_id in new_measures:
            if NorhanEntity.is_measure_id_supported(measure_id):
                if not self._new_measure_signal_name:
                    self._new_measure_signal_name = (
                        f"{DOMAIN}_measure_available_meterid_{meter_id}"
                    )
                entity = NorhanEntity(
                    measure_id,
                    measure_data,
                    self._new_measure_signal_name,
                    self._scale_factor,
                )
                new_enitities.append(entity)
            else:
                _LOGGER.debug("Ignore unhandled measure_id %s", measure_id)
        return new_enitities
