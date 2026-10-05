import pytest

from app.core.production_security import validate_production_security


def test_development_keeps_local_defaults():
    validate_production_security({"APP_ENV": "development"})


def production():
    return {"APP_ENV": "production", "CORS_ALLOW_ORIGINS": "https://travel.example.com",
            "TRIP_ALLOWED_ORIGINS": "https://travel.example.com", "TRIP_CAPABILITY_COOKIE_SECURE": "true"}


def test_secure_production_is_accepted():
    validate_production_security(production())


def test_startup_rejects_unsafe_configuration_before_calling_provider(monkeypatch):
    from app.main import check_runtime_capabilities
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TRIP_CAPABILITY_COOKIE_SECURE", "false")
    monkeypatch.setattr("app.main.enforce_poi_discovery_configuration",
                        lambda: pytest.fail("Provider must not be called before config validation"))
    with pytest.raises(ValueError, match="TRIP_CAPABILITY_COOKIE_SECURE"):
        check_runtime_capabilities()


@pytest.mark.parametrize("field,value", [
    ("CORS_ALLOW_ORIGINS", "*"), ("TRIP_ALLOWED_ORIGINS", ""),
    ("TRIP_ALLOWED_ORIGINS", "http://travel.example.com"),
    ("TRIP_ALLOWED_ORIGINS", "https://travel.example.com/path"),
    ("CORS_ALLOW_ORIGINS", "https://user:password@travel.example.com"),
    ("TRIP_CAPABILITY_COOKIE_SECURE", "false"),
])
def test_unsafe_production_fails_without_exposing_values(field, value):
    with pytest.raises(ValueError) as error:
        validate_production_security({**production(), field: value})
    assert field in str(error.value)
    assert "password" not in str(error.value)
