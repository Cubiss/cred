from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any, Dict

from .base import Provider, ProviderInfo
from ..errors import Locked, NotFound, ProviderMissing, ConfigError

log = logging.getLogger("cred.providers.op")


class OpProvider(Provider):
    """1Password provider restricted to vault `cred`.

    Backend storage model:
      - Each locator maps to ONE 1Password item in vault `cred`.
      - The item's concealed custom field named `data` stores a JSON object string
        (e.g. {"user":"...","pass":"..."}).
      - get/set operate on keys within that JSON object.
      - Special field names: "data" / "json" read or replace the entire JSON blob.

    Locator accepted formats:
      - "<item title or id>"           (recommended)
      - "op://cred/<item title or id>" (allowed; vault must be cred)
      - "op://<other-vault>/..."       (rejected)
    """

    VAULT = "cred"
    DATA_FIELD = "data"
    WHOLE_BLOB_FIELDS = {"data", "json"}

    def __init__(self) -> None:
        if shutil.which("op") is None:
            raise ProviderMissing("1Password CLI 'op' not found in PATH")

    @property
    def info(self) -> ProviderInfo:
        try:
            p = subprocess.run(["op", "--version"], check=True, capture_output=True, text=True)
            ver = p.stdout.strip()
        except Exception:
            ver = None
        return ProviderInfo(name="op", version=ver)

    # -------------------------
    # Helpers
    # -------------------------

    def _enforce_cred_locator(self, locator: str) -> str:
        loc = locator.strip()
        if loc.startswith("op://"):
            prefix = f"op://{self.VAULT}/"
            if not loc.startswith(prefix):
                raise ConfigError(
                    f"OpProvider is restricted to vault '{self.VAULT}', got locator: {locator!r}"
                )
            return loc[len(prefix) :]
        return loc

    def _classify_error(self, stderr: str) -> Exception:
        err = (stderr or "").lower()
        if ("not signed in" in err) or ("sign in" in err) or ("authentication" in err) or ("locked" in err):
            return Locked("1Password CLI is locked / not signed in")
        if (
            ("not found" in err)
            or ("no item" in err)
            or ("could not find" in err)
            or ("isn't an item" in err)
            or ("is not an item" in err)
            or ("isnt an item" in err)
        ):
            return NotFound("Item or field not found")
        return RuntimeError(stderr)

    def _run(self, args: list[str], *, stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
        try:
            log.debug("op exec: %s", " ".join(args[:4]) + (" ..." if len(args) > 4 else ""))
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

    def _get_data_blob_from_item_json(self, item_json: dict[str, Any]) -> str:
        fields = item_json.get("fields")
        if not isinstance(fields, list):
            return "{}"
        for f in fields:
            if not isinstance(f, dict):
                continue
            if f.get("id") == self.DATA_FIELD or f.get("label") == self.DATA_FIELD:
                v = f.get("value")
                return v if isinstance(v, str) else "{}"
        return "{}"

    def _get_item_json(self, item: str) -> dict[str, Any]:
        out = self._run(["op", "item", "get", "--vault", self.VAULT, item, "--format", "json"]).stdout
        return json.loads(out)

    def _create_item(self, title: str) -> dict[str, Any]:
        # Create a Secure Note item (no secrets in argv).
        out = self._run(
            ["op", "item", "create", "--vault", self.VAULT, "--category", "Secure Note", "--title", title, "--format", "json"]
        ).stdout
        return json.loads(out)

    def _ensure_data_field(self, item_json: dict[str, Any]) -> None:
        fields = item_json.get("fields")
        if not isinstance(fields, list):
            item_json["fields"] = []
            fields = item_json["fields"]

        for f in fields:
            if not isinstance(f, dict):
                continue
            if f.get("id") == self.DATA_FIELD or f.get("label") == self.DATA_FIELD:
                f.setdefault("type", "CONCEALED")
                f.setdefault("value", "{}")
                f.setdefault("label", self.DATA_FIELD)
                f.setdefault("id", self.DATA_FIELD)
                return

        fields.append({"id": self.DATA_FIELD, "label": self.DATA_FIELD, "type": "CONCEALED", "value": "{}"})

    def _write_item_json(self, item_id_or_title: str, item_json: dict[str, Any]) -> None:
        # Edit using piped JSON so secrets aren’t passed as argv.
        self._run(
            ["op", "item", "edit", "--vault", self.VAULT, item_id_or_title],
            stdin_text=json.dumps(item_json, ensure_ascii=False),
        )

    def _load_kv(self, item_json: dict[str, Any], *, item_label: str) -> dict[str, str]:
        raw = self._get_data_blob_from_item_json(item_json).strip()
        if not raw:
            return {}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Stored data field is not valid JSON for item {item_label!r}: {e}") from e
        if not isinstance(obj, dict):
            raise ConfigError(f"Stored data JSON must be an object for item {item_label!r}")

        out: dict[str, str] = {}
        for k, v in obj.items():
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
        return out

    # -------------------------
    # Provider diagnostics (optional)
    # -------------------------

    def doctor(self) -> Dict[str, str]:
        """Return a small diagnostics report. Never includes secrets."""
        report: Dict[str, str] = {}
        report["op.in_path"] = "yes"
        report["vault"] = self.VAULT

        # Signed-in / unlocked check
        try:
            self._run(["op", "whoami"])
            report["op.signed_in"] = "yes"
        except Locked:
            report["op.signed_in"] = "no (locked)"
            return report
        except Exception:
            report["op.signed_in"] = "unknown"

        # Vault existence check
        try:
            self._run(["op", "vault", "get", self.VAULT])
            report["vault.exists"] = "yes"
        except NotFound:
            report["vault.exists"] = "no"
        except Exception:
            report["vault.exists"] = "unknown"

        return report

    # -------------------------
    # Provider API
    # -------------------------

    def exists(self, locator: str) -> bool:
        item = self._enforce_cred_locator(locator)
        try:
            _ = self._get_item_json(item)
            return True
        except NotFound:
            return False

    def get(self, locator: str, field: str) -> str:
        item = self._enforce_cred_locator(locator)
        item_json = self._get_item_json(item)

        if field in self.WHOLE_BLOB_FIELDS:
            return self._get_data_blob_from_item_json(item_json)

        kv = self._load_kv(item_json, item_label=item)
        if field not in kv:
            raise NotFound(f"Key {field!r} not found in JSON blob for item {item!r}")
        return kv[field]

    def set(self, locator: str, field: str, value: str, *, create: bool = False) -> None:
        item = self._enforce_cred_locator(locator)

        # Ensure item exists (create if requested)
        try:
            item_json = self._get_item_json(item)
            item_id = item_json.get("id", item)
            log.info("op item exists: %r", item)
        except NotFound:
            if not create:
                raise
            log.info("op creating item: %r", item)
            created = self._create_item(item)
            item_json = created
            item_id = created.get("id", item)

        # Ensure the `data` field exists
        self._ensure_data_field(item_json)

        # Compute new blob
        if field in self.WHOLE_BLOB_FIELDS:
            try:
                obj = json.loads(value) if value.strip() else {}
            except json.JSONDecodeError as e:
                raise ConfigError(f"Value for {field!r} must be valid JSON: {e}") from e
            if not isinstance(obj, dict):
                raise ConfigError(f"Value for {field!r} must be a JSON object (not {type(obj).__name__})")
            new_blob = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        else:
            kv = self._load_kv(item_json, item_label=item)
            kv[field] = value
            new_blob = json.dumps(kv, ensure_ascii=False, separators=(",", ":"))

        # Write new_blob into the `data` field
        for f in item_json.get("fields", []):
            if isinstance(f, dict) and (f.get("id") == self.DATA_FIELD or f.get("label") == self.DATA_FIELD):
                f["type"] = "CONCEALED"
                f["value"] = new_blob
                f.setdefault("label", self.DATA_FIELD)
                f.setdefault("id", self.DATA_FIELD)
                break
        else:
            item_json.setdefault("fields", []).append(
                {"id": self.DATA_FIELD, "label": self.DATA_FIELD, "type": "CONCEALED", "value": new_blob}
            )

        self._write_item_json(str(item_id), item_json)
