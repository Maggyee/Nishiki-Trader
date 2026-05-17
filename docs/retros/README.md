# Retros

ADR-007 §2.6 promotion-review records and other post-action retros.

## Purpose

Every change to a `(source, model_version)` `SourcePolicy` — including the
explicit decision to **not** change a policy — must be backed by a structured
review artifact. This directory is where those artifacts live.

ADR-007 §2.6 mandates seven sections per review: source/model, current vs
target policy, bundle path / manifest fingerprint, signals & lineage,
execution outcome, runtime hygiene, conclusion. The
`apps.strategies_nautilus.runners.promotion_review` CLI generates all seven
sections from a paper bundle and a small set of operator inputs.

## File-naming convention

```
docs/retros/<UTC date>-<source>-<model_version_or_short_id>-<decision>-<target_stage>.md
```

Examples:

- `2026-05-17-freqai-linear-v1-hold-paper-shadow.md`
- `2026-08-01-freqai-linear-v1-promote-paper-simulated.md`
- `2026-09-12-rule-baseline-v1-disable-after-kill-switch.md`

Use the literal `decision` value from the CLI (`promote`, `hold`, `demote`,
`disable`). Use UTC dates so files sort chronologically.

## How to generate a record

1. Run a paper bundle for the source under review with the current
   `SourcePolicy`. The bundle must be `kind="paper"` with
   `runtime.mode="paper"`, `runtime.data_mode="catalog_polling"`,
   `runtime.order_mode="simulated"`. Phase 2 only supports
   `catalog_polling` paper bundles; Phase 3 will add wall-clock paper
   before testnet promotion is allowed.

2. Run the review CLI:

   ```bash
   UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.promotion_review \
     <bundle_dir> \
     --current-stage <current_stage> \
     --target-stage <target_stage> \
     --current-dry-run|--current-no-dry-run \
     --current-position-pct-multiplier <float> \
     [--current-min-confidence-override <float|none>] \
     --target-dry-run|--target-no-dry-run \
     --target-position-pct-multiplier <float> \
     [--target-min-confidence-override <float|none>] \
     --decision promote|hold|demote|disable \
     --operator <name> \
     --rationale "<text>" \
     --output-markdown docs/retros/<UTC>-<source>-<model>-<decision>-<target_stage>.md
   ```

   Stages are: `backtest_baseline`, `paper_shadow`, `paper_simulated`,
   `testnet_canary`, `live_canary`, `live_normal`. Phase 2 hard-blocks any
   target above `paper_simulated`.

3. Inspect the generated Markdown. The CLI's exit code is `0` only when
   the requested transition passes every hard gate (no
   `review_blockers`, no `promotion_gate_blockers`, valid stage move,
   bundle policy matches `current_policy`). A non-zero exit code means
   the artifact was still written but the decision is **not** allowed —
   read the `decision_reasons` and either fix the bundle / decision or
   document why the gate disagrees with you.

4. Commit the Markdown together with the code or config change it
   authorizes. The retro is the audit record; without it, any
   `SourcePolicy` change to that source/model is unsigned.

## Hard rules (mirrored from ADR-007 §2.6)

- A review with `review_blockers != []` cannot promote. Fix the bundle
  (rerun without `git_dirty`, fix sidecar mismatches, eliminate
  expired/unauthorized/lagging/kill-switch/data-gap signals) or downgrade
  the decision to hold/demote/disable.
- A `promote` decision must move exactly one stage up and present an
  explicit `policy_diff` (current_policy != target_policy).
- A `hold` decision must keep stage and policy identical.
- A `demote` decision must end at the same or earlier stage and never
  loosen `dry_run` or raise the multiplier.
- A `disable` decision is always allowed — surfacing any open bundle
  issues for audit — and the target policy must be at zero multiplier
  or `dry_run=True`.
- `paper_shadow → paper_simulated` requires ≥ 50 signals OR ≥ 7
  inclusive session days **and** a bundle clean of review blockers.

## Existing entries

- [`2026-05-17-freqai-linear-v1-hold-paper-shadow.md`](2026-05-17-freqai-linear-v1-hold-paper-shadow.md)
  — first retro. `freqai_linear_v1 / linear-mom-train20240105` held at
  `paper_shadow` because the source emits only 7 signals across 7 days
  (below the ≥ 50 threshold) even though the shadow bundle is clean.
