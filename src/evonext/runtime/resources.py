"""Read-only resource selection against a single owner's inventory observation."""
from abc import ABC, abstractmethod
from collections.abc import Callable
from time import time
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evonext.contracts.runtime import TargetKind

Driver = Literal["external_agent", "builtin_agent", "cloud_query"]
ResourceId = Annotated[str, Field(min_length=1, max_length=128)]


class ResourceRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    driver: Driver | None = None
    resource_id: ResourceId | None = None
    capabilities: frozenset[str] = frozenset()


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_id: ResourceId
    unit: Literal["device", "pool"]
    drivers: frozenset[Driver] = Field(min_length=1)
    capabilities: frozenset[str] = frozenset()
    state: Literal["available", "busy", "offline", "cleaning", "unknown"]
    available_slots: int | None = Field(ge=0)
    accepts_queue: bool = False

    @model_validator(mode="after")
    def check_capacity(self):
        if self.unit == "device" and self.available_slots not in (0, 1, None):
            raise ValueError("A physical device has at most one slot")
        if self.state == "available" and not self.available_slots:
            raise ValueError("Available capacity must be positive and observed")
        if self.state == "unknown" and self.available_slots is not None:
            raise ValueError("Unknown capacity must have null available_slots")
        if self.state in ("busy", "offline", "cleaning") and self.available_slots != 0:
            raise ValueError("An unavailable resource has zero available slots")
        return self


class Inventory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: TargetKind
    observed_at_epoch: int
    expires_at_epoch: int
    resources: tuple[Resource, ...]

    @model_validator(mode="after")
    def check_inventory(self):
        if self.observed_at_epoch >= self.expires_at_epoch:
            raise ValueError("Inventory needs a positive validity window")
        if len({r.resource_id for r in self.resources}) != len(self.resources):
            raise ValueError("Duplicate resource in inventory")
        return self


class ResourcePool(ABC):
    """The reader supplies one consistent observation. Listing never reserves a slot."""

    kind: ClassVar[TargetKind]

    def __init__(self, read_inventory: Callable[[], Inventory]):
        self._read_inventory = read_inventory

    @abstractmethod
    def _validate_resources(self, inventory: Inventory) -> None:
        """Check the units and capabilities the resource owner can advertise."""

    def inventory(self) -> Inventory:
        observation = self._read_inventory()
        if observation.kind != self.kind:
            raise ValueError("Inventory belongs to another resource pool")
        self._validate_resources(observation)
        return observation

    def list_available(
        self, requirements: ResourceRequirements, *, now: float | None = None,
    ) -> Inventory:
        inventory = self.inventory()
        timestamp = time() if now is None else now
        if not inventory.observed_at_epoch <= timestamp < inventory.expires_at_epoch:
            raise ValueError("Resource inventory is outside its validity window")
        matches = tuple(
            item for item in inventory.resources
            if item.state == "available"
            and (requirements.driver is None or requirements.driver in item.drivers)
            and (requirements.resource_id is None or requirements.resource_id == item.resource_id)
            and requirements.capabilities <= item.capabilities
        )
        return inventory.model_copy(update={"resources": matches})


class LocalDevicePool(ResourcePool):
    kind = "local_device"

    def _validate_resources(self, inventory: Inventory) -> None:
        for device in inventory.resources:
            if device.unit != "device" or "cloud_query" in device.drivers or device.accepts_queue:
                raise ValueError("Local inventory requires physical devices and local drivers")


class CloudBatchPool(ResourcePool):
    kind = "cloud_batch"

    def _validate_resources(self, inventory: Inventory) -> None:
        if len({item.unit for item in inventory.resources}) > 1:
            raise ValueError("Report cloud devices or pool capacities at one granularity")


def get_resource_pool(kind: TargetKind, read_inventory: Callable[[], Inventory]) -> ResourcePool:
    if kind == "local_device":
        return LocalDevicePool(read_inventory)
    if kind == "cloud_batch":
        return CloudBatchPool(read_inventory)
    raise ValueError(f"Unsupported resource pool: {kind}")
