# cred

A tiny credential broker with pluggable backends.

It gives your scripts a stable interface (`cred get/set/exists`) while keeping the actual storage provider swappable.
Right now it supports **1Password** via the `op` CLI, with all secrets stored in a dedicated vault named **`cred`**.

## Backend model

For portability across providers, the 1Password backend stores **one JSON blob per reference** in a single concealed custom field named `data`.

- `cred set <ref> --field pass ...` updates a key inside that JSON object.
- `cred get-json <ref>` / `cred set-json <ref>` operate on the whole blob.

## Features

- Pluggable credential backends (current: **1Password** via `op`)
- Provider-agnostic interface for scripts: `cred get`, `cred set`, `cred exists`
- Whole-blob operations: `cred get-json`, `cred set-json`
- Safe inspection: `cred dump` (redacted by default)
- Diagnostics: `cred doctor`
- Safe input: `cred set --prompt` (no-echo), or `--value -` to read from stdin
- Optional config indirection via `[map]` (can be omitted)
- Logging: `--verbose`, `--debug`, or `CRED_LOG_LEVEL`

## Install

Recommended for personal CLI tools: **pipx**.

```bash
pipx install git+https://github.com/Cubiss/cred.git
```

Or with pip:

```bash
pip install --user git+https://github.com/Cubiss/cred.git
```

## Requirements

- Python 3.11+
- `op` (1Password CLI) available in `PATH` for the `op` provider
- A 1Password vault named **`cred`**

## 1Password setup

1. Create a vault named **`cred`** in the 1Password app.
2. Install the 1Password CLI (`op`) and sign in.
3. Optional: enable “Integrate with 1Password CLI” in the desktop app for a smoother flow.

Quick sanity checks:

```bash
op --version
op whoami
op vault get cred
```

## Configuration

Create `~/.config/cred/config.toml`:

```toml
provider = "op"
```

Maps are **optional**. If you want an indirection layer (rename items later, use UUIDs, etc.):

```toml
provider = "op"

[map]
"transmission/rpc" = "Transmission RPC"
```

Field aliases are also optional:

```toml
[fields]
pass = "pass"
user = "user"
```

## Usage

### Read a key

```bash
cred get transmission/rpc --field user
cred get transmission/rpc --field pass
```

### Set a key

Secure prompt (no echo):

```bash
cred set transmission/rpc --field pass --prompt --create
```

From stdin (useful for pipelines):

```bash
printf '%s' 'supersecret' | cred set transmission/rpc --field pass --value - --create
```

### Work with the whole JSON blob

```bash
cred get-json transmission/rpc
printf '%s' '{"user":"alice","pass":"secret"}' | cred set-json transmission/rpc --value - --create
```

## Exit codes

- `0` success
- `10` not found (unknown ref / missing key / missing item)
- `11` locked / authentication required (e.g. `op` not signed in)
- `12` provider missing (e.g. `op` not installed)
- `13` configuration error

### Inspect without leaking secrets

Dump redacted JSON (default):

```bash
cred dump transmission/rpc
```

Only keys:

```bash
cred dump transmission/rpc --keys
```

Raw dump (dangerous):

```bash
cred dump transmission/rpc --raw
```

### Diagnostics

```bash
cred doctor
```

## Logging

- `--verbose` enables INFO logs
- `--debug` enables DEBUG logs
- or set `CRED_LOG_LEVEL=debug`

Logs never print secret values (by design).
