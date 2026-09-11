# Ed25519 testnet credentials and first signed account read — 2026-09-11

Status: **operator-provided local credentials validated; signed Spot testnet account
read succeeded**. This advances the
[testnet environment selection](portfolio-spot-testnet-selection-2026-09-11.md).
It does not qualify the account baseline, key restrictions, user-stream continuity,
or a trading restart.

## Local configuration

The operator generated an Ed25519 pair using OpenSSL and identified the files in
the project directory. The private key and existing env both have mode 0600; both
PEM files are ignored by Git. Local OpenSSL derivation confirms the public/private
pair matches. No private key, API key or signature was displayed or committed.

The existing API-key-only `~/.config/trader/binance_testnet.env` was preserved and
one path assignment appended and fsynced:

```text
BINANCE_TESTNET_API_KEY='<existing testnet API key, retained locally>'
BINANCE_TESTNET_PRIVATE_KEY_PATH='/home/orca/orca/projects/trader/ed25519_private.pem'
```

This is the new read-only credential loader's format. No HMAC
`BINANCE_TESTNET_API_SECRET` is needed, and the private PEM remains in its original
file. The old canary runner's credential format and trading permissions are not
changed; do not feed this configuration into a trading runner.

`load_testnet_ed25519_credentials` reads only the explicitly selected absolute
config path and referenced absolute private-key path. Files must be bounded,
owned by the process user, regular, private and not symlinks. Config parsing accepts
literal assignments (including quoted paths and optional `export`) without shell
execution or environment expansion. Extra/duplicate fields, HMAC secrets and
endpoint overrides fail. Credential object representations omit both secret fields.

The parser accepts the exact seed-only unencrypted Ed25519 PKCS#8 container produced
by `openssl genpkey -algorithm ED25519` (RFC 8410, OID 1.3.101.112), then normalizes
PEM formatting for the installed native signers. Other key types, encrypted keys,
public-key files and unsupported containers fail; no blind last-32-byte conversion
is used to qualify an arbitrary input. No new Python dependency was introduced.

## Native signing integration

The installed native HTTP client's `_get_sign` checks for an HMAC `api_secret`
before checking its explicit Ed25519 key. Setting `api_secret=None` and supplying
`ed25519_private_key` therefore still raises an error in that upstream method.

The project-owned `Ed25519TestnetReadOnlyHttpClient` overrides only signing dispatch,
using the native Rust `ed25519_signature` function and refusing missing Ed25519
state. It retains the existing account-only GET whitelist, bounded I/O and sanitized
errors; it never falls back to HMAC. The factory fixes the host to Spot testnet.
Upstream source and installed packages are unchanged.

The existing native WebSocket signer accepts normalized PEM through its
`api_secret` argument and detects Ed25519. `create_clients` wires HTTP and WS from
the same loaded material, while the existing journal source-binding check remains.
Independent OpenSSL verification covers an actual native HTTP signature and an
actual native signed-subscription request through a local test transport. External
WebSocket authentication was not attempted in this increment.

## First external read and retained evidence

After offline signing tests passed, one bounded signed `GET /api/v3/account` with
`omitZeroBalances=false` was issued through the account-only HTTP extension to
`https://testnet.binance.vision`. Testnet accepted the Ed25519 signature and returned
a SPOT account containing a UID and **502 asset balance records**.

The full raw response was retained locally, with its response hash, request/receipt
times, endpoint and API-key fingerprint. The new artifact was created exclusively
with mode 0600, fsynced along with its directory, and remains ignored:

```text
data/spot-testnet-initial-account-20260911T014024Z.json
SHA256: 205cf2a16badecf973889f5de92ceede53d902d294d92eec565ff060f6c422cc
```

The wrapper uses `portfolio.testnet_initial_account_observation.v1`; it is an
initial observation, not a `CollectedAccount` or a completed stream-journal
collection. It retains `expected_uid=null`, `uid_match_verified=false`,
`baseline_qualified=false`, `api_key_restrictions_verified=false` and
`runtime_ready=false`. The returned UID is observed from this request and has not
been compared with an independently supplied identity. The snapshot cannot become
a retrospective recovery baseline merely by selecting its current hash.

The 502 assets are preserved in full. No BTC/USDT-only projection, allocation,
500-USDT substitution, order, cancellation, execution client, strategy startup or
production request was performed. Successful `/api` reading does not establish
the absent `/sapi` API-key restriction evidence. The strict collector still rejects
missing permissions rather than interpreting this standalone read as its completion.

## Verification and remaining scope

**19 new tests pass**: native HTTP/WS signatures verified independently by OpenSSL,
no HMAC fallback, testnet endpoint selection, input immutability and safe repr,
ambiguous config/shell/endpoint rejection, private file permissions, symlinks, size
bounds, absent files and wrong/truncated key containers. Tests generate disposable
synthetic keys; the user's keys are never used by the test suite.

Local operator files were validated without disclosure and matched as a pair.
The one external signed account read is separate from the offline test suite.

Full offline suite: **2,213 passed**, 12 PostgreSQL integration tests deselected
without a dedicated integration DSN. Ruff, registry and whitespace checks pass.

```bash
.venv/bin/pytest -q tests/strategies_nautilus/test_portfolio_testnet_credentials.py
.venv/bin/pytest -q -m 'not network and not postgres'
.venv/bin/ruff check apps tests notebooks
.venv/bin/python -m apps.ops.research_family_registry --check
git diff --check
```

Next: build the explicit full-account testnet observation/archive workflow and
qualify a bounded native WS session with this key; keep unknown key restrictions
explicit. Then establish a selected account identity and independent baseline,
handle testnet reset boundaries, and qualify the mapping into native recovery.
The existing dedicated flat BTC/USDT fixture is not a description of the observed
502-asset account. No risk rule, SignalEvent v1, SourcePolicy or trading path changes.
