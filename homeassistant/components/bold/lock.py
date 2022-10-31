"""Lock entity for Bold Smart Lock."""
import datetime
import logging
import math
from typing import Any

from bold_smart_lock.enums import DeviceType

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_MODEL, CONF_NAME, CONF_TYPE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .const import (
    CONF_ACTUAL_FIRMWARE_VERSION,
    CONF_BATTERY_LAST_MEASUREMENT,
    CONF_BATTERY_LEVEL,
    CONF_MAKE,
    CONF_PERMISSION_REMOTE_ACTIVATE,
    DOMAIN,
)
from .coordinator import BoldCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create Bold Smart Lock entities."""
    coordinator: BoldCoordinator = hass.data[DOMAIN][entry.entry_id]

    locks = list(
        filter(
            lambda d: d[CONF_TYPE][CONF_ID] == DeviceType.LOCK.value
            and d[CONF_PERMISSION_REMOTE_ACTIVATE],
            coordinator.data,
        )
    )
    print("locks", locks)
    async_add_entities(
        BoldLockEntity(coordinator=coordinator, data=lock) for lock in locks
    )


class BoldLockEntity(CoordinatorEntity, LockEntity):
    """Bold Smart Lock entity."""

    def __init__(self, coordinator: BoldCoordinator, data):
        """Init Bold Smart Lock entity."""
        super().__init__(coordinator)
        self._data = data
        self._coordinator: BoldCoordinator = coordinator
        self._attr_name = data[CONF_NAME]
        self._attr_unique_id = data[CONF_ID]
        self._unlock_end_time = dt_util.utcnow()
        self._attr_extra_state_attributes = {
            "battery_level": data[CONF_BATTERY_LEVEL],
            "battery_last_measurement": data[CONF_BATTERY_LAST_MEASUREMENT],
        }

    @property
    def device_info(self):
        """Return the device information for this entity."""
        return DeviceInfo(
            {
                "identifiers": {(DOMAIN, self._attr_unique_id)},
                "name": self._attr_name,
                "manufacturer": self._data[CONF_MODEL][CONF_MAKE],
                "model": self._data[CONF_MODEL][CONF_MODEL],
                "sw_version": self._data[CONF_ACTUAL_FIRMWARE_VERSION],
                "via_device": (DOMAIN, self._attr_unique_id),
            }
        )

    @property
    def is_locked(self) -> bool:
        """Return the status of the lock."""
        return dt_util.utcnow() >= self._unlock_end_time

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock Bold Smart Lock."""
        try:
            activation_response = await self._coordinator.bold.remote_activation(
                self._attr_unique_id
            )
            if activation_response:
                self._unlock_end_time = dt_util.utcnow() + datetime.timedelta(
                    seconds=activation_response["activationTime"]
                )
                self.update_state()
                _LOGGER.debug(
                    "Lock deactivated, scheduled activation of lock after %s seconds",
                    activation_response["activationTime"],
                )
                async_track_point_in_utc_time(
                    self.hass, self.update_state, self._unlock_end_time
                )
        except Exception as exception:
            raise HomeAssistantError(
                f"Error while unlocking: {self._attr_name}"
            ) from exception

    def lock(self, **kwargs: Any) -> None:
        """Lock Bold Smart Lock."""
        seconds_to_go = math.ceil(
            (self._unlock_end_time - dt_util.utcnow()).total_seconds()
        )
        raise HomeAssistantError(
            f"Manual locking not available yet, {self._attr_name} will automatically lock in {seconds_to_go} seconds"
        )

    @callback
    def update_state(self, _=dt_util.utcnow()):
        """Request new state update."""
        self.async_write_ha_state()
