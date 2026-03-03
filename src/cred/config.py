from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

DEFAULT_PATH = Path.home() / ".config" / "cred" / "config.toml"

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


@dataclass(frozen=True)
class CredConfig:
    provider: str
    mapping: dict[str, str]
    fields: dict[str, str]


def load_config(path: Path | None = None) -> CredConfig:
    p = path or DEFAULT_PATH
    if not p.exists():
        raise ConfigError(f"Config not found: {p}")

    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ConfigError(f"Failed to parse config: {p}: {e}") from e

    provider = data.get("provider")
    if not isinstance(provider, str) or not provider:
        raise ConfigError("Missing config key: provider")

    mapping = data.get("map", {})
    if not isinstance(mapping, dict):
        raise ConfigError("Config key [map] must be a table")

    fields = data.get("fields", {})
    if not isinstance(fields, dict):
        raise ConfigError("Config key [fields] must be a table")

    return CredConfig(
        provider=provider,
        mapping={str(k): str(v) for k, v in mapping.items()},
        fields={str(k): str(v) for k, v in fields.items()},
    )
