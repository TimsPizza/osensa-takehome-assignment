import json
import sys
from typing import TypedDict

from app.models import CODEGEN_TARGETS, SchemaMode


class ExportedContract(TypedDict):
    name: str
    mode: SchemaMode
    schema: dict[str, object]


def _inline_local_references(schema: dict[str, object]) -> dict[str, object]:
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        return schema

    prefix = "#/$defs/"

    def resolve(value: object, resolving: frozenset[str]) -> object:
        if isinstance(value, list):
            return [resolve(item, resolving) for item in value]
        if not isinstance(value, dict):
            return value

        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith(prefix):
            definition_name = reference.removeprefix(prefix)
            if definition_name in resolving:
                raise ValueError(f"recursive contract schema is not supported: {definition_name}")
            definition = definitions.get(definition_name)
            if not isinstance(definition, dict):
                raise ValueError(
                    f"contract schema references unknown definition: {definition_name}"
                )
            siblings = {key: item for key, item in value.items() if key != "$ref"}
            return {
                **resolve(definition, resolving | {definition_name}),
                **resolve(siblings, resolving),
            }

        return {key: resolve(item, resolving) for key, item in value.items() if key != "$defs"}

    resolved = resolve(schema, frozenset())
    if not isinstance(resolved, dict):
        raise TypeError("resolved contract schema must be an object")
    return resolved


def export_contracts() -> list[ExportedContract]:
    return [
        {
            "name": model.__name__,
            "mode": mode,
            "schema": _inline_local_references(model.model_json_schema(by_alias=True, mode=mode)),
        }
        for model, mode in CODEGEN_TARGETS
    ]


def main() -> None:
    json.dump({"models": export_contracts()}, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
