import re
from typing import Any, Dict
import jsonschema
from jsonschema.exceptions import SchemaError
from app.core.exceptions import ValidationError

TOOL_ID_PATTERN = re.compile(r"^[a-z0-9_\-\.]{3,64}$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9_\.]+)?$")


def validate_input_schema(schema: Dict[str, Any]) -> None:
    """Validates that the provided dictionary is a structurally valid JSON Schema."""
    if not isinstance(schema, dict):
        raise ValidationError("Tool input_schema must be a valid JSON dictionary.")

    if not schema:
        raise ValidationError("Tool input_schema cannot be empty.")

    # Must specify a type (usually 'object')
    if "type" not in schema:
        raise ValidationError("Tool input_schema must specify a root 'type' (e.g. 'object').")

    try:
        # Check against standard Draft-7 / Draft 2020-12 validator
        jsonschema.Draft202012Validator.check_schema(schema)
    except SchemaError as err:
        raise ValidationError(f"Invalid JSON Schema definition: {err.message}", details={"error": str(err)})


def validate_tool_metadata(
    tool_id: str,
    name: str,
    version: str,
    executor_key: str,
) -> None:
    """Validates identifier formats and mandatory naming conventions."""
    if not TOOL_ID_PATTERN.match(tool_id):
        raise ValidationError(
            f"Invalid tool_id '{tool_id}'. Must be 3-64 characters, lowercase alphanumeric, underscore, dot, or dash."
        )

    if not name or len(name.strip()) < 3:
        raise ValidationError("Tool name must be at least 3 characters long.")

    if not VERSION_PATTERN.match(version):
        raise ValidationError(
            f"Invalid version format '{version}'. Must follow semantic versioning (e.g. '1.0.0')."
        )

    if not executor_key or len(executor_key.strip()) < 2:
        raise ValidationError("Executor key cannot be empty.")

