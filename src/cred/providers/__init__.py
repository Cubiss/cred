from .base import Provider
from .one_password import OpProvider

PROVIDERS: dict[str, type[Provider]] = {
    "op": OpProvider,
}

