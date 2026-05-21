from .base import Provider
from .one_password import OpProvider
from .proton_pass import ProtonPassProvider

PROVIDERS: dict[str, type[Provider]] = {
    "op": OpProvider,
    "proton": ProtonPassProvider,
}

