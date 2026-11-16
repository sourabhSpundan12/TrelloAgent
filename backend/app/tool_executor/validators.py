from typing import Any, Dict
import jsonschema
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from app.tool_executor.exceptions import ToolInputValidationError


def validate_parameters_against_schema(parameters: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """Validates execution parameters against the tool's registered JSON Schema."""
    if not isinstance(schema, dict) or not schema:
        return

    try:
        jsonschema.validate(instance=parameters, schema=schema)
    except JSONSchemaValidationError as err:
        loc = " -> ".join(str(p) for p in err.absolute_path) or "root"
        raise ToolInputValidationError(
            f"Validation failed for parameter '{loc}': {err.message}",
            details={"field": loc, "error": err.message, "schema_path": list(err.schema_path)},
        )

