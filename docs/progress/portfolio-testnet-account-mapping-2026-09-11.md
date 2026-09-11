# Full-account testnet comparison and isolated native mapping — 2026-09-11

The operator confirms that the key already exists and there is no other program
or manual trading. No additional account records were supplied. Reset/faucet
history remains unknown; the brief reply is not independent UID verification or
proof of a complete no-trade history. Existing local Ed25519 credentials were
reused without displaying, copying or modifying their values.

## New observations

The existing bounded observation entrypoint ran from clean commit `a8c1f99`.
Two signed Spot testnet WS subscriptions, four full-account collections and
explicit reconnect passed over **24.157 seconds**. Every collection retained
**502 assets**, with zero account-wide open orders. Zero business events arrived.
All four observations replayed exactly in a separate process without credentials.

Comparing the final collection with the selected prior final collection found:

- Zero added or removed assets.
- Zero free/locked balance changes, including non-BTC/USDT assets.
- Identical account-wide open orders and non-balance account fields.

Equal endpoints do not prove nothing happened between them. No conclusion about
missing events, reset history, trading PnL or account equity follows. The current
observation remains `baseline_qualified=false` and `runtime_ready=false`.

## Native mapping

An unsigned, bounded GET to the official testnet `/api/v3/exchangeInfo` returned
**1,363 symbols**. All 502 observed assets have a single consistent asset precision
across these listings. The installed native registry initially recognizes only
45 of them; the other 457 are not errors in Binance balances and must not be
silently dropped or assigned the parser's default eight-place precision.

`portfolio_testnet_mapping.py` constructs explicit metadata-derived currencies,
checks exact free/locked/total Money conversion, and compares the complete native
CashAccount balance map against the selected observation. All **502/502** match
without rounding. Missing metadata, conflicting precision or inexact amounts
prevent complete account construction; no partial account is accepted.

Native account construction registers currencies internally. This operation is
therefore isolated in a fresh Python process with a 30-second bound and private
stdin/stdout pipes. The parent registry remains unchanged. The constructed
AccountState is explicitly `reported=false` and marked diagnostic. It is not an
exchange event, restored execution account, persistent checkpoint or live adapter.
No engine, strategy, subscription or order client is created by the mapper.

This is numeric representation acceptance. Currency classification, tradability,
valuation, commissions, order filters and native adapter lifecycle are not thereby
qualified. Public listing metadata is captured separately from account reads;
its execution freshness is not certified. Its hash proves local integrity, not
an atomic account/venue revision. No 500 USDT planning substitution occurs.

## Review entrypoint and retained evidence

`apps.ops.portfolio_testnet_account_review` replays both explicitly selected
archives before comparison. It validates shared observed source identity, pinned
hashes, collection identities and forward non-overlapping intervals. Asset names,
including Unicode, free/locked differences, additions/removals, order differences
and changed account metadata fields are preserved. The optional pinned exchange
metadata enables isolated mapping. Without it, the native registry diagnostic
reports unresolved currencies explicitly.

Detailed output is created exclusively with mode 0600. Existing files are never
overwritten. Stdout contains counts/digests, not balances, UID, keys or raw responses.
Exit 0 means the diagnostic completed; even an equal report never grants readiness.
The separate strict collector continues to require its existing evidence and
cannot accept these observation reports as a recovery permit.

All following artifacts are private and Git-ignored:

| Artifact under `data/` | SHA256 |
|---|---|
| `spot-testnet-observation-20260911T024828Z.jsonl` | `b6dbfebf126add7a332d38c310a12c17bbee647fc290d5097804c18ca9ba12d7` |
| `spot-testnet-observation-20260911T024828Z-summary.json` | `7aee74e17f7ede6eff9a71c4291dcadad3a3994a801e19a02240f2b68560858a` |
| `spot-testnet-exchange-info-20260911T024828Z.json` | `616c89b8a49eef321325a6fbbc53859845a861464657e0ad7fb514e3cf1d241f` |
| `spot-testnet-account-mapping-isolated-20260911T024828Z.json` | `f7081f46c96a146defa9f43de819ea8a98edce2ea4f29673d1c594560282ad8a` |

The metadata filename groups this observation session; its wrapper contains its
actual separate request/receipt timestamps. The final comparison selects prior
collection `185007e9-d583-46dc-b16e-5dc78f0214d0` from the
[prior pinned archive](portfolio-testnet-observation-2026-09-11.md), and new
collection `74ec21f7-7a58-4548-bbcf-23ab1c551fe0`. Both use initial selection
SHA256 `205cf2a16badecf973889f5de92ceede53d902d294d92eec565ff060f6c422cc`.
Intermediate registry-only and pre-isolation diagnostics remain local historical
outputs; they are not the selected final mapping report.

CLI reproduction takes `--before-archive`, `--before-sha256`,
`--before-collection`, corresponding `--after-*`, `--selection-sha256`, optional
paired `--exchange-info` / `--exchange-info-sha256`, and a fresh `--output` path.
It performs no network access and never loads credentials.

## Verification and next step

**78 focused tests passed**, including new comparison and mapping tests plus the
existing full-account observation suite. Tests cover unknown/Unicode assets,
free-to-locked moves with unchanged totals, metadata/order drift, exact hashes,
source changes, reversed intervals, precision conflicts/loss, whole-account
mapping, parent registry isolation, private outputs and refusal to overwrite.
Full offline regression: **2,313 passed**, 12 Postgres integration tests
deselected because no dedicated integration DSN was supplied. Ruff, the research
family registry and whitespace checks pass. The final isolated CLI diagnostic
was run against the pinned real observation and public metadata artifacts.

Next qualify a testnet-specific identity/permission and prospective baseline
contract using available evidence, explicitly retaining unavailable `/sapi`
restrictions and unknown resets. Independent records are currently unavailable;
repeating the same quiet observations will not supply that evidence. Business
events, downtime history, full-asset valuation and actual adapter process recovery
still require separate acceptance. Neither this operator reply nor the numeric
mapping starts testnet orders or restores the demoted legacy canary.

Changed files: `apps/ops/portfolio_testnet_account_review.py`,
`apps/strategies_nautilus/portfolio_testnet_mapping.py`, their test file
`tests/ops/test_portfolio_testnet_account_review.py`, the two application READMEs,
this report, `docs/agent-reading-list.md` and `docs/project-status.md`.
Upstream source, credentials, strict recovery gates, SourcePolicy, schedules,
ADR-015 risk settings and live trading paths are untouched.
