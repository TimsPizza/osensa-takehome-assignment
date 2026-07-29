from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel

type SchemaMode = Literal["validation", "serialization"]


class WireModel(BaseModel):
    """Base policy for JSON messages that cross the MQTT boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=False,
        serialize_by_alias=True,
    )


class OrderRequested(WireModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    order_id: UUID = Field(alias="orderId")
    table_id: int = Field(alias="tableId", strict=True, ge=1, le=4)
    food_name: str = Field(
        alias="foodName",
        strict=True,
        min_length=1,
        max_length=100,
        pattern=r"^\S(?:.*\S)?$",
    )


class OrderStatusBase(WireModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    order_id: UUID = Field(alias="orderId")
    table_id: int = Field(alias="tableId", strict=True, ge=1, le=4)
    food_name: str = Field(
        alias="foodName",
        strict=True,
        min_length=1,
        max_length=100,
        pattern=r"^\S(?:.*\S)?$",
    )
    occurred_at: AwareDatetime = Field(alias="occurredAt")


class OrderQueued(OrderStatusBase):
    status: Literal["queued"]


class OrderProcessing(OrderStatusBase):
    status: Literal["processing"]


class FoodReady(OrderStatusBase):
    status: Literal["food_ready"]
    ready_at: AwareDatetime = Field(alias="readyAt")


type OrderFailureCode = Literal["processing_failed", "service_overloaded"]


class OrderFailed(OrderStatusBase):
    status: Literal["failed"]
    code: OrderFailureCode
    message: str = Field(strict=True, min_length=1, max_length=200)
    retryable: bool = Field(strict=True)


type OrderStatusUpdate = Annotated[
    OrderQueued | OrderProcessing | FoodReady | OrderFailed,
    Field(discriminator="status"),
]


class OrderStatusChanged(RootModel[OrderStatusUpdate]):
    model_config = ConfigDict(frozen=True)


class TableSnapshot(WireModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    service_instance_id: UUID = Field(alias="serviceInstanceId")
    table_id: int = Field(alias="tableId", strict=True, ge=1, le=4)
    revision: int = Field(strict=True, ge=0)
    generated_at: AwareDatetime = Field(alias="generatedAt")
    orders: tuple[OrderStatusUpdate, ...] = Field(max_length=10)


class KitchenWorkerIdle(WireModel):
    worker_id: int = Field(alias="workerId", strict=True, ge=1, le=64)
    status: Literal["idle"]


class KitchenWorkerProcessing(WireModel):
    worker_id: int = Field(alias="workerId", strict=True, ge=1, le=64)
    status: Literal["processing"]
    order_id: UUID = Field(alias="orderId")
    table_id: int = Field(alias="tableId", strict=True, ge=1, le=4)
    food_name: str = Field(
        alias="foodName",
        strict=True,
        min_length=1,
        max_length=100,
        pattern=r"^\S(?:.*\S)?$",
    )


type KitchenWorkerState = Annotated[
    KitchenWorkerIdle | KitchenWorkerProcessing,
    Field(discriminator="status"),
]


class KitchenPressureSnapshot(WireModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    service_instance_id: UUID = Field(alias="serviceInstanceId")
    revision: int = Field(strict=True, ge=0)
    generated_at: AwareDatetime = Field(alias="generatedAt")
    queued_orders: int = Field(alias="queuedOrders", strict=True, ge=0)
    queue_capacity: int = Field(alias="queueCapacity", strict=True, ge=1, le=10_000)
    workers: tuple[KitchenWorkerState, ...] = Field(min_length=1, max_length=64)


# Explicit roots prevent internal Pydantic models from leaking into the frontend contract.
CODEGEN_TARGETS: Final[tuple[tuple[type[BaseModel], SchemaMode], ...]] = (
    (OrderRequested, "validation"),
    (OrderStatusChanged, "serialization"),
    (TableSnapshot, "serialization"),
    (KitchenPressureSnapshot, "serialization"),
)
