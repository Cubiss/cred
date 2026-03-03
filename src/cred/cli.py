from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from pathlib import Path

from .config import load_config
from .errors import CredError, ConfigError
from .logging_utils import setup_logging
from .resolver import resolve_locator, get_provider

log = logging.getLogger("cred.cli")


def _read_stdin_value() -> str:
    # If stdin is a TTY, read a single line so users don't need Ctrl+D.
    # If piped, read the entire stream.
    if sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    return sys.stdin.read().rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cred")
    parser.add_argument("--config", help="Path to config.toml (default: ~/.config/cred/config.toml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable informational logging")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging (never prints secrets)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_get = sub.add_parser("get", help="Get a credential field for a reference")
    p_get.add_argument("ref")
    p_get.add_argument("--field", required=True, help="Field/key name (or alias from config)")

    p_set = sub.add_parser("set", help="Set a credential field for a reference")
    p_set.add_argument("ref")
    p_set.add_argument("--field", required=True, help="Field/key name (or alias from config)")

    val_group = p_set.add_mutually_exclusive_group(required=True)
    val_group.add_argument("--value", help="Value to set. Use '-' to read from stdin.")
    val_group.add_argument("--prompt", action="store_true", help="Prompt securely for the value (no echo).")

    p_set.add_argument(
        "--create",
        action="store_true",
        help="Create the item/locator if it doesn't exist (provider-dependent).",
    )

    p_exists = sub.add_parser("exists", help="Check if a reference exists")
    p_exists.add_argument("ref")

    sub.add_parser("provider", help="Print active provider")

    p_get_json = sub.add_parser("get-json", help="Print the full JSON blob for a reference")
    p_get_json.add_argument("ref")

    p_set_json = sub.add_parser("set-json", help="Replace the full JSON blob for a reference")
    p_set_json.add_argument("ref")
    json_val_group = p_set_json.add_mutually_exclusive_group(required=True)
    json_val_group.add_argument("--value", help="JSON value to set. Use '-' to read from stdin.")
    json_val_group.add_argument("--file", type=Path, help="Read JSON from a file path.")
    p_set_json.add_argument("--create", action="store_true", help="Create item if it doesn't exist.")
    p_set_json.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON before storing (normalizes formatting).",
    )

    p_dump = sub.add_parser("dump", help="Show stored JSON (redacted by default)")
    p_dump.add_argument("ref")
    p_dump.add_argument("--raw", action="store_true", help="Print raw JSON (DANGEROUS: prints secrets)")
    p_dump.add_argument("--redact", action="store_true", help="Redact values (default)")
    p_dump.add_argument("--keys", action="store_true", help="Only print top-level keys")

    sub.add_parser("doctor", help="Run provider diagnostics (no secrets printed)")

    args = parser.parse_args(argv)

    setup_logging(verbose=args.verbose, debug=args.debug)
    log.debug("argv parsed cmd=%s", args.cmd)

    try:
        cfg = load_config(None if args.config is None else Path(args.config))
        provider = get_provider(cfg)
        log.info("provider=%s", cfg.provider)

        if args.cmd == "provider":
            print(cfg.provider)
            return 0

        if args.cmd == "doctor":
            # Generic checks
            print("cred doctor")
            print(f"  provider: {cfg.provider}")
            try:
                info = getattr(provider, "info", None)
                if info is not None:
                    pi = provider.info
                    print(f"  provider.version: {pi.version or 'unknown'}")
            except Exception as e:
                log.debug("failed reading provider info: %s", e)

            # Provider-specific checks if available
            doc_fn = getattr(provider, "doctor", None)
            if callable(doc_fn):
                report = doc_fn()
                for k, v in report.items():
                    print(f"  {k}: {v}")
            else:
                print("  note: provider has no doctor() implementation")
            return 0

        locator = resolve_locator(cfg, args.ref) if hasattr(args, "ref") else None

        if args.cmd == "exists":
            locator = resolve_locator(cfg, args.ref)
            ok = provider.exists(locator)
            return 0 if ok else 10

        if args.cmd == "get":
            locator = resolve_locator(cfg, args.ref)
            field = cfg.fields.get(args.field, args.field)
            log.debug("get ref=%r locator=%r field=%r", args.ref, locator, field)
            val = provider.get(locator, field)
            sys.stdout.write(val)
            sys.stdout.write("\n")
            return 0

        if args.cmd == "set":
            locator = resolve_locator(cfg, args.ref)
            field = cfg.fields.get(args.field, args.field)

            if args.prompt:
                value = getpass.getpass(f"{field}: ")
            else:
                if args.value == "-":
                    value = _read_stdin_value()
                else:
                    value = args.value

            log.debug("set ref=%r locator=%r field=%r create=%s", args.ref, locator, field, args.create)
            provider.set(locator, field, value, create=args.create)
            return 0

        if args.cmd == "get-json":
            locator = resolve_locator(cfg, args.ref)
            log.debug("get-json ref=%r locator=%r", args.ref, locator)
            sys.stdout.write(provider.get(locator, "json"))
            sys.stdout.write("\n")
            return 0

        if args.cmd == "set-json":
            locator = resolve_locator(cfg, args.ref)
            if args.file is not None:
                raw = args.file.read_text(encoding="utf-8")
            else:
                raw = _read_stdin_value() if args.value == "-" else args.value

            # Validate JSON object
            try:
                obj = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError as e:
                raise ConfigError(f"Invalid JSON: {e}") from e
            if not isinstance(obj, dict):
                raise ConfigError("JSON blob must be an object")

            final = json.dumps(obj, ensure_ascii=False, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":"))
            log.debug("set-json ref=%r locator=%r create=%s pretty=%s", args.ref, locator, args.create, args.pretty)
            provider.set(locator, "json", final, create=args.create)
            return 0

        if args.cmd == "dump":
            locator = resolve_locator(cfg, args.ref)
            raw = provider.get(locator, "json")
            try:
                obj = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                # If stored data isn't valid JSON, show a safe hint.
                raise ConfigError("Stored blob is not valid JSON (refusing to print raw blob)") from None

            if args.keys:
                for k in sorted(obj.keys()):
                    print(k)
                return 0

            redact = args.redact or not args.raw
            if redact:
                redacted = {k: "***" for k in obj.keys()}
                print(json.dumps(redacted, ensure_ascii=False, indent=2))
            else:
                # Raw printing is explicitly opted in.
                print(json.dumps(obj, ensure_ascii=False, indent=2))
            return 0

        raise ConfigError("Unknown command")  # shouldn't happen

    except CredError as e:
        print(str(e), file=sys.stderr)
        return e.exit_code
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
