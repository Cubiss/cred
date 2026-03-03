from __future__ import annotations
from .config import CredConfig
from .errors import ConfigError
from .providers import PROVIDERS

def resolve_locator(cfg: CredConfig, ref: str) -> str:
    return cfg.mapping.get(ref, ref)

def get_provider(cfg: CredConfig):
    cls = PROVIDERS.get(cfg.provider)
    if cls is None:
        raise ConfigError(f"Unknown provider: {cfg.provider}")
    return cls()
