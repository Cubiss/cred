from __future__ import annotations

# Proton Pass provider using the official `pass-cli` binary.
#
# Storage model:
#   - Each locator maps to one custom item in vault `cred`.
#   - A hidden field named `data` (in section "cred") stores a JSON object string
#     (e.g. '{"user":"...","pass":"..."}').
#   - get/set operate on keys within that JSON object.
#   - Special field names "data" / "json" read or replace the entire blob.
#   - Item creation uses `--from-template -` (stdin) — blob never appears in argv.
#   - Item update uses `--field data=<blob>` (argv) — unavoidable with current CLI.
#
# Authentication:
#   There is no shared agent with the Proton Pass desktop app.
#   Authenticate once with `pass-cli login` or `pass-cli login --pat pst_<token>::<key>`.
#   Use `pass-cli test` to verify the session.

import json
import logging
import shutil
import subprocess
from typing import Any, Dict

from .base import Provider, ProviderInfo
from ..errors import Locked, NotFound, ProviderMissing, ConfigError

log = logging.getLogger("cred.providers.proton_pass")


class ProtonPassProvider(Provider):
    """Proton Pass provider restricted to vault `cred`."""

    BINARY = "pass-cli"
    VAULT = "cred"
    DATA_FIELD = "data"
    SECTION = "cred"
    WHOLE_BLOB_FIELDS = {"data", "json"}

    def __init__(self) -> None:
        if shutil.which(self.BINARY) is None:
            raise ProviderMissing(f"Proton Pass CLI '{self.BINARY}' not found in PATH")

    @property
    def info(self) -> ProviderInfo:
        try:
            p = subprocess.run(
                [self.BINARY, "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
            ver = p.stdout.strip()
        except Exception:
            ver = None
        return ProviderInfo(name="proton", version=ver)

    # -------------------------
    # Helpers
    # -------------------------

    def _classify_error(self, stderr: str) -> Exception:
        log.debug(stderr)

        err = (stderr or "").lower()
        if "this operation requires an authenticated client" in err:
            return Locked("Proton Pass CLI is not authenticated — run: pass-cli login")
        if "no item found" in err:
            return NotFound("Item not found")
        return RuntimeError(stderr.strip())

    def _run(
        self, args: list[str], *, stdin_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            log.debug(
                "pass-cli exec: %s",
                " ".join(args[:10]) + (" ..." if len(args) > 10 else ""),
            )
            return subprocess.run(
                args,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                input=stdin_text,
            )
        except subprocess.CalledProcessError as e:
            raise self._classify_error(e.stderr) from e

    def _read_blob(self, item: str) -> str:
        """Return the hidden data field value for an item (the raw JSON blob string)."""
        out = self._run([
            self.BINARY, "item", "view",
            "--vault-name", self.VAULT,
            "--item-title", item,
            "--field", self.DATA_FIELD,
        ]).stdout.strip()
        return out or "{}"

    def _write_blob(self, item: str, blob: str) -> None:
        """Overwrite the hidden data field on an existing item."""
        self._run([
            self.BINARY, "item", "update",
            "--vault-name", self.VAULT,
            "--item-title", item,
            "--field", f"{self.DATA_FIELD}={blob}",
        ])

    def _create_item(self, title: str, blob: str) -> None:
        """Create a new custom item with a hidden `data` field, passing the blob via stdin."""
        template = {
            "title": title,
            "note": "",
            "sections": [
                {
                    "section_name": self.SECTION,
                    "fields": [
                        {
                            "field_name": self.DATA_FIELD,
                            "field_type": "hidden",
                            "value": blob,
                        }
                    ],
                }
            ],
        }
        self._run(
            [self.BINARY, "item", "create", "custom",
             "--vault-name", self.VAULT,
             "--from-template", "-"],
            stdin_text=json.dumps(template, ensure_ascii=False),
        )

    def _load_kv(self, blob: str, *, item_label: str) -> dict[str, str]:
        raw = blob.strip()
        if not raw:
            return {}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ConfigError(
                f"Stored data is not valid JSON for item {item_label!r}: {e}"
            ) from e
        if not isinstance(obj, dict):
            raise ConfigError(
                f"Stored data must be a JSON object for item {item_label!r}"
            )
        return {k: v for k, v in obj.items() if isinstance(k, str) and isinstance(v, str)}

    # -------------------------
    # Provider diagnostics
    # -------------------------

    def doctor(self) -> Dict[str, str]:
        report: Dict[str, str] = {}
        report["pass-cli.in_path"] = "yes"
        report["vault"] = self.VAULT

        try:
            self._run([self.BINARY, "test"])
            report["pass-cli.authenticated"] = "yes"
        except Locked:
            report["pass-cli.authenticated"] = "no — run: pass-cli login"
            return report
        except Exception:
            report["pass-cli.authenticated"] = "unknown"

        try:
            out = self._run([self.BINARY, "vault", "list", "--output", "json"]).stdout
            vaults: list[Any] = json.loads(out)
            names = [v.get("name", "") for v in vaults if isinstance(v, dict)]
            report["vault.exists"] = "yes" if self.VAULT in names else "no"
        except Exception:
            report["vault.exists"] = "unknown"

        return report

    # -------------------------
    # Provider API
    # -------------------------

    def exists(self, locator: str) -> bool:
        try:
            self._read_blob(locator)
            return True
        except NotFound:
            return False

    def get(self, locator: str, field: str) -> str:
        blob = self._read_blob(locator)

        if field in self.WHOLE_BLOB_FIELDS:
            return blob

        kv = self._load_kv(blob, item_label=locator)
        if field not in kv:
            raise NotFound(f"Key {field!r} not found in blob for item {locator!r}")
        return kv[field]

    def set(self, locator: str, field: str, value: str, *, create: bool = False) -> None:
        try:
            current_blob = self._read_blob(locator)
            item_exists = True
        except NotFound:
            if not create:
                raise
            current_blob = "{}"
            item_exists = False
            log.info("proton pass: creating item %r", locator)

        if field in self.WHOLE_BLOB_FIELDS:
            try:
                obj = json.loads(value) if value.strip() else {}
            except json.JSONDecodeError as e:
                raise ConfigError(f"Value for {field!r} must be valid JSON: {e}") from e
            if not isinstance(obj, dict):
                raise ConfigError(
                    f"Value for {field!r} must be a JSON object (not {type(obj).__name__})"
                )
            new_blob = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        else:
            kv = self._load_kv(current_blob, item_label=locator)
            kv[field] = value
            new_blob = json.dumps(kv, ensure_ascii=False, separators=(",", ":"))

        if item_exists:
            self._write_blob(locator, new_blob)
        else:
            self._create_item(locator, new_blob)
