from __future__ import annotations

import logging
import os


def setup_logging(*, verbose: bool = False, debug: bool = False) -> None:
    """Configure stderr logging for the CLI.

    Never log secret values. Callers should only log metadata (refs, fields, provider names, etc.).
    """
    level = logging.WARNING
    if verbose:
        level = logging.INFO
    if debug:
        level = logging.DEBUG

    env = os.getenv("CRED_LOG_LEVEL")
    if env:
        level = getattr(logging, env.upper(), level)

    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )
