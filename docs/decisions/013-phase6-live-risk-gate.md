# ADR-013: Phase 6 Live Risk Gate

- **Status**: Draft
- **Date**: 2026-06-29
- **Owner**: nishiki
- **Scope**: Phase 6 entry conditions for the first small-money Binance Spot live canary.
- **Depends on**: ADR-001, ADR-002, ADR-006, ADR-007, ADR-008.

## 1. Context

Phase 5 is active as a read-only operations dashboard and monitoring surface.
The next phase in `docs/agent-operating-contract.md` is Phase 6: small-money
live trading. Phase 6 is not open yet.

Current blockers are deliberate:

- ADR-001 requires testnet -> 100-500 USDT -> 1,000 USDT -> larger capital only
  after three profitable months.
- ADR-001 requires the 5% single-day-loss kill-switch at every real-money
  stage.
- ADR-008 requires 14 consecutive qualified testnet days before live money.
- `docs/progress/phase-3-testnet-continuity-plan.md` currently records
  `current_qualified_streak_days=0/14`.
- `freqai_linear_v1 / linear-mom-train20240105` is held at
  `testnet_canary`; no live promotion review exists.

This ADR defines the gate that must be satisfied before Phase 6 can be opened.
It does not authorize live trading, does not introduce live credentials, and
does not change `SourcePolicy`.

## 2. Decision

Phase 6 entry requires all of the following evidence, in this order:

1. A passive `report_testnet_bundle --continuity` review over the full candidate
   window, including blocked completed bundles, with:
   - `required_gate_met=true`;
   - `current_qualified_streak_days >= 14`;
   - `kill_switch_alerts=0`;
   - `emergency_flatten_completed_alerts=0`;
   - `restart_drift_days=[]`.
2. A live-risk ADR acceptance update to this file or its successor, changing
   status from Draft to Accepted only after human go/no-go review.
3. A signed `promotion_review.py` artifact for the exact
   `(source, model_version)` moving `testnet_canary -> live_canary`.
   The artifact must be structured JSON or the standard Markdown form with
   `decision=promote`, `decision_allowed=yes`, non-empty `operator`,
   `review_blockers=none`, and `promotion_gate_blockers=none`; incidental text
   mentions of stage names do not count.
4. A declared starting capital between 100 and 500 USDT, spot-only, no margin,
   no leverage.
5. An accepted operator runbook for the first live day, including:
   - preflight clean git check;
   - credential load and key-prefix-only audit;
   - emergency flatten command and manual exchange fallback;
   - first-hour observation cadence;
   - post-run retro template.
6. A startup guard that refuses live mode unless all required evidence paths are
   supplied, the git tree is clean, the saved readiness report is fresh, and
   `--allow-live-credentials` is explicit.

Until every item is satisfied, Phase 6 remains closed and the live path remains
blocked.

## 3. Allowed Work Before Acceptance

Allowed before this ADR is Accepted:

- passive readiness reports;
- read-only dashboard or document links showing live-readiness blockers;
- tests for startup-guard behavior using fake credentials or injected clients;
- runbook drafts;
- promotion-review dry runs that do not mutate policy.

Forbidden before this ADR is Accepted:

- loading live Binance credentials from project code;
- connecting NautilusTrader to a live Binance account;
- placing live orders;
- adding frontend controls that trigger live runners, promotion reviews, or
  emergency flatten;
- allowing LLM agents to write `SignalEvent`, mutate `SourcePolicy`, or call
  exchange APIs.

## 4. Readiness Tools

`python -m apps.ops.live_readiness` is the passive gate reader for this ADR. It
emits `phase6.live_readiness.v1` JSON or Markdown from:

- `docs/project-status.md`;
- this ADR status;
- optional completed testnet bundle directories passed to the existing passive
  continuity reader;
- an optional live-canary promotion-review artifact path;
- an explicit starting-capital declaration.
- an explicit market-scope declaration, which must remain Binance Spot only,
  no margin, and max leverage 1.0.
- the git commit and dirty/clean state at report generation time.
- SHA-256 fingerprints for the exact project-status and live-risk ADR bytes
  the readiness report consumed.
- SHA-256 fingerprints for every supplied testnet continuity bundle
  `run_manifest.json` artifact, including the manifest path the startup guard
  must reread.
- the SHA-256 fingerprint of the exact live promotion-review artifact bytes
  when that artifact is present and parseable.

The tool is audit-only. It never loads exchange credentials, starts a runtime,
changes `SourcePolicy`, writes `SignalEvent`, places orders, or authorizes live
trading by itself.

Example blocked review:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.live_readiness \
  --source freqai_linear_v1 \
  --model-version linear-mom-train20240105 \
  --starting-capital-usdt 100 \
  --market-type spot \
  --max-leverage 1 \
  --markdown
```

`python -m apps.strategies_nautilus.runners.live_startup_guard` is the passive
startup preflight reader for a future live runner. It consumes a saved
`phase6.live_readiness.v1` JSON report plus the live-risk ADR, live-canary
promotion review, first-live-day runbook, capital declaration, live SourcePolicy
fields, live market scope, explicit `--allow-live-credentials`, and git state.
It parses the promotion review as `promotion_review.py` JSON or Markdown fields
and requires exact `source`, `model_version`, `current_stage=testnet_canary`,
`target_stage=live_canary`, `decision=promote`, `decision_allowed=yes`,
non-empty `operator`, and no review or promotion gate blockers.
It also rejects any saved readiness report whose passive boundary flags are not
all closed, whose recorded git commit does not match the startup guard's
current clean commit, whose recorded project-status SHA-256 does not match the
project-status artifact supplied to startup, whose recorded live-risk ADR
SHA-256 does not match the ADR artifact supplied to startup, whose recorded
live promotion-review SHA-256 does not match the artifact supplied to startup,
whose recorded continuity bundle manifest SHA-256 does not match the current
local manifest bytes, or whose `generated_at_ns` is missing, in the future, or
older than the guard's maximum accepted age. The
default maximum age is 24 hours, overrideable with
`--max-readiness-report-age-seconds` only when the operator intentionally
widens the evidence window. It returns exit code 2 when the future live runner
must refuse startup.
The startup-guard report records the SHA-256 of the saved readiness report
artifact it actually read, so dashboard and retro review can identify the exact
preflight input bytes. It also records the SHA-256 fingerprints of the
live-risk ADR and first-live-day runbook artifacts it read, so an operator can
prove the startup decision was made against the intended human-review
documents.

The startup-guard report records the startup-side project-status SHA-256 it
expected the readiness report to match. The startup guard still does not load
live credentials, inspect credential values, build a Nautilus node, connect to
Binance, mutate `SourcePolicy`, write `SignalEvent`, place orders, or
authorize live trading. It only defines the startup refusal contract before
those capabilities exist.

Current blocked example:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m \
  apps.strategies_nautilus.runners.live_startup_guard \
  --mode live \
  --kind live \
  --allow-live-credentials \
  --source freqai_linear_v1 \
  --model-version linear-mom-train20240105 \
  --policy-position-pct-multiplier 0.1 \
  --starting-capital-usdt 100 \
  --market-type spot \
  --max-leverage 1 \
  --max-readiness-report-age-seconds 86400 \
  --live-readiness-report-path docs/retros/<phase6-live-readiness>.json \
  --live-promotion-review-path docs/retros/<live-canary-promotion-review>.md \
  --first-live-day-runbook-path docs/runbook-first-live-day.md \
  --markdown
```

When live-readiness evidence collection resumes, pass every completed
manifest-backed bundle in the candidate continuity window:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.live_readiness \
  --source freqai_linear_v1 \
  --model-version linear-mom-train20240105 \
  --starting-capital-usdt 100 \
  --market-type spot \
  --max-leverage 1 \
  --continuity-bundle data/testnet/<run_id-1> \
  --continuity-bundle data/testnet/<run_id-N> \
  --markdown
```

## 5. Phase 6 Startup Guard Requirements

A future live runner must refuse startup unless:

- `--mode live` and `--kind live` are both explicit;
- `--allow-live-credentials` is present;
- git status is clean and matches the committed evidence;
- this ADR or its successor is Accepted;
- a saved `phase6.live_readiness.v1` report proves the 14-day continuity gate
  and has no blockers, was generated from a clean git tree, and records the
  same commit as startup preflight;
- the saved readiness report records SHA-256 fingerprints for every testnet
  continuity bundle manifest used to prove the 14-day continuity gate;
- every recorded continuity bundle `manifest_path` exists locally at startup
  and hashes to the readiness report's recorded SHA-256;
- the saved readiness report has `generated_at_ns` and is no older than the
  guard's configured maximum age, default 24 hours;
- the saved readiness report records project-status and live-risk ADR
  SHA-256 fingerprints;
- the saved readiness report's recorded project-status SHA-256 exactly matches
  the project-status artifact supplied to the startup guard;
- the saved readiness report's recorded live-risk ADR SHA-256 exactly matches
  the live-risk ADR artifact supplied to the startup guard;
- the startup-guard report records the SHA-256 fingerprint of the saved
  readiness report artifact it consumed;
- the startup-guard report records SHA-256 fingerprints for the live-risk ADR
  and first-live-day runbook artifacts it consumed;
- the saved readiness report records `live_promotion_review.sha256`, and that
  SHA-256 exactly matches the live promotion-review artifact supplied to the
  startup guard;
- a live-canary promotion review exists for the exact source/model transition
  `testnet_canary -> live_canary`, with `decision=promote`,
  `decision_allowed=yes`, a non-empty operator, and no review or promotion gate
  blockers;
- starting capital is declared and within 100-500 USDT;
- market scope is declared as Binance Spot only, no margin, and no leverage;
- `SourcePolicy.dry_run=false`;
- `SourcePolicy.position_pct_multiplier <= 0.1`;
- an accepted first-live-day runbook exists;
- emergency flatten has a tested live-mode path or an explicit manual exchange
  fallback checklist.

The passive live startup guard is implemented and unit-tested, but it is not
wired to a live runner and does not open Phase 6 by itself.

## 6. Deferred

- Implementing live Binance adapter wiring.
- Storing or loading live Binance credentials.
- Opening `live_canary` or `live_normal` stages.
- Increasing capital beyond the first 100-500 USDT bracket.
- Any frontend write/control surface.

## 7. Acceptance Checklist

This ADR can move from Draft to Accepted only when:

- the 14-day continuity gate is proven from bundle artifacts;
- the first-live-day runbook exists;
- the live startup guard is implemented and tested;
- the operator signs a live go/no-go decision;
- `docs/project-status.md` is updated to record Phase 6 entry as still blocked
  or explicitly open.

Until then, Phase 6 is not open.
