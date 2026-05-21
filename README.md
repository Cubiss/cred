# cred

A tiny credential broker with pluggable backends.

It gives your scripts a stable interface (`cred get/set/exists`) while keeping the actual storage provider swappable.
Supports **1Password** (`op`) and **Proton Pass** (`proton`), with all secrets stored in a dedicated vault named **`cred`**.

## Backend model

Both providers store **one JSON blob per reference** in a single concealed/hidden custom field named `data`.

- `cred set <ref> --field pass ...` updates a key inside that JSON object.
- `cred get-json <ref>` / `cred set-json <ref>` operate on the whole blob.

## Features

- Pluggable credential backends: **1Password** (`op`), **Proton Pass** (`proton`)
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
- `op` (1Password CLI) in `PATH` — for the `op` provider
- `pass-cli` (Proton Pass CLI) in `PATH` — for the `proton` provider
- A vault named **`cred`** in your chosen provider

## Provider setup

### 1Password

1. Create a vault named **`cred`** in the 1Password app.
2. Install the 1Password CLI (`op`) and sign in.
3. Optional: enable “Integrate with 1Password CLI” in the desktop app for biometric unlock.

```bash
op --version
op whoami
op vault get cred
```

### Proton Pass

1. Create a vault named **`cred`** in Proton Pass.
2. Install `pass-cli` and authenticate:

```bash
pass-cli login               # browser-based (default)
pass-cli login --interactive # username + password
pass-cli login --pat pst_<token>::<key>  # personal access token
```

3. Verify the session:

```bash
pass-cli test
```

There is no shared session with the Proton Pass desktop app — the CLI manages its own session.

## Configuration

Create `~/.config/cred/config.toml` and set your provider:

```toml
# 1Password
provider = "op"
```

```toml
# Proton Pass
provider = "proton"
```

Maps are **optional**. If you want an indirection layer (rename items later, use UUIDs, etc.):

```toml
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

You can override the configured provider for any call with `--provider`:

```bash
cred --provider proton get transmission/rpc --field user
cred --provider op    get transmission/rpc --field user
```

### Read a key

```bash
cred get transmission/rpc --field user
cred get transmission/rpc --field pass
```

### Set a key

Secure prompt (no echo):

```bash
cred set transmission/rpc --field pass --prompt
```

From stdin (useful for pipelines):

```bash
printf '%s' 'supersecret' | cred set transmission/rpc --field pass --value -
```

Pass `--no-create` to fail instead of creating a new item when the reference doesn't exist yet.

### Work with the whole JSON blob

```bash
cred get-json transmission/rpc
printf '%s' '{"user":"alice","pass":"secret"}' | cred set-json transmission/rpc --value -
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
