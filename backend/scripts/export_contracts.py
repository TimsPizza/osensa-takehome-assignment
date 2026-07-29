import json
import sys
from typing import TypedDict

from app.models import CODEGEN_TARGETS, SchemaMode


class ExportedContract(TypedDict):
    name: str
    mode: SchemaMode
    schema: dict[str, object]


def export_contracts() -> list[ExportedContract]:
    return [
        {
            "name": model.__name__,
            "mode": mode,
            "schema": model.model_json_schema(by_alias=True, mode=mode),
        }
        for model, mode in CODEGEN_TARGETS
    ]


def main() -> None:
    json.dump({"models": export_contracts()}, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
