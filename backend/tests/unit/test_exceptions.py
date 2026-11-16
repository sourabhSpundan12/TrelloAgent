from app.core.exceptions import (
    AppException,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DatabaseConnectionError,
    NotFoundError,
    ValidationError,
)


def test_app_exception_base():
    exc = AppException("Custom base error message", status_code=418, error_code="TEAPOT_ERROR", details={"brew": "earl_grey"})
    assert exc.status_code == 418
    assert exc.error_code == "TEAPOT_ERROR"
    data = exc.to_dict()
    assert data["error"]["code"] == "TEAPOT_ERROR"
    assert data["error"]["message"] == "Custom base error message"
    assert data["error"]["details"] == {"brew": "earl_grey"}


def test_authentication_error():
    exc = AuthenticationError("Invalid email or password.")
    assert exc.status_code == 401
    assert exc.error_code == "AUTHENTICATION_FAILED"
    data = exc.to_dict()
    assert data["error"]["code"] == "AUTHENTICATION_FAILED"
    assert data["error"]["message"] == "Invalid email or password."


def test_authorization_error():
    exc = AuthorizationError("Role 'EMPLOYEE' not permitted.")
    assert exc.status_code == 403
    assert exc.error_code == "PERMISSION_DENIED"


def test_not_found_error():
    exc = NotFoundError("User account not found.")
    assert exc.status_code == 404
    assert exc.error_code == "RESOURCE_NOT_FOUND"


def test_conflict_error():
    exc = ConflictError("Email already in use.")
    assert exc.status_code == 409
    assert exc.error_code == "RESOURCE_CONFLICT"


def test_validation_error():
    exc = ValidationError("Invalid parameter.", details={"field": "email"})
    assert exc.status_code == 422
    assert exc.error_code == "VALIDATION_ERROR"
    assert exc.details == {"field": "email"}


def test_database_connection_error():
    exc = DatabaseConnectionError("MongoDB ping timeout.")
    assert exc.status_code == 503
    assert exc.error_code == "DATABASE_UNAVAILABLE"
