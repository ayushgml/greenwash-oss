import pytest

from config import validate


def test_minimal_config_is_valid():
    assert validate({"name": "api", "port": 8080}) == {"name": "api", "port": 8080}


def test_optional_timeout_is_accepted():
    cfg = {"name": "api", "port": 8080, "timeout": 2.5}
    assert validate(cfg) == cfg


def test_bad_port_rejected():
    with pytest.raises(ValueError, match="port"):
        validate({"name": "api", "port": 70000})
