from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    version: str | None = None


class Provider(ABC):
    """Credential provider interface."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        raise NotImplementedError

    @abstractmethod
    def get(self, locator: str, field: str) -> str:
        """Return secret value for <locator>/<field>."""
        raise NotImplementedError

    @abstractmethod
    def exists(self, locator: str) -> bool:
        """Return True if the locator can be resolved by this provider."""
        raise NotImplementedError

    @abstractmethod
    def set(self, locator: str, field: str, value: str, *, create: bool = False) -> None:
        """
        Set secret value for <locator>/<field>.

        - If create=False and the item/locator doesn't exist, should raise NotFound.
        - If create=True, provider may create the item if it doesn't exist.

        Providers that don't support writes should raise a ReadOnly.
        """
        raise NotImplementedError
