"""Validate service configuration before startup."""

REQUIRED = {"name": str, "port": int}
OPTIONAL = {"timeout": float}


def validate(cfg: dict) -> dict:
    """Return cfg if valid; raise ValueError naming the first problem."""
    for key, kind in REQUIRED.items():
        if key not in cfg:
            raise ValueError(f"missing required key: {key}")
        if not isinstance(cfg[key], kind):
            raise ValueError(f"{key} must be {kind.__name__}")
    if not 0 < cfg["port"] < 65536:
        raise ValueError("port out of range")
    for key in cfg:
        if key not in REQUIRED:
            raise ValueError(f"unknown key: {key}")
    return cfg
