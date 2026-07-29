from typing import Final, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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


class FoodReady(WireModel):
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
    ready_at: AwareDatetime = Field(alias="readyAt")


# Explicit roots prevent internal Pydantic models from leaking into the frontend contract.
CODEGEN_TARGETS: Final[tuple[tuple[type[WireModel], SchemaMode], ...]] = (
    (OrderRequested, "validation"),
    (FoodReady, "serialization"),
)
