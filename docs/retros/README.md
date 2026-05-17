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
- [`2026-05-17-freqai-linear-v1-hold-paper-shadow-31d.md`](2026-05-17-freqai-linear-v1-hold-paper-shadow-31d.md)
  — second retro on the same `(source, model_version)` after the
  catalog was extended to 31 days. 308 shadow signals over 31 inclusive
  days clear both halves of the ADR-007 §2.5 OR-gate. Decision is still
  `hold` because the 308-signal evidence is in-sample on January 2024
  — the model was trained on the same month, so a hold-out window
  (e.g., 2024-02 forward) is needed before any `promote` decision.
- [`2026-05-17-freqai-linear-v1-hold-paper-shadow-60d-holdout.md`](2026-05-17-freqai-linear-v1-hold-paper-shadow-60d-holdout.md)
  — third retro after the catalog was extended to 60 days. 595 shadow
  signals (308 January + 287 February). February is the first fully
  held-out month for this `(source, model_version)`. Signal-side
  distributional comparison Jan vs Feb is near-identical (density,
  long-share, score/confidence quantiles), so the model survives the
  one-month regime shift on signal generation. Decision is still
  `hold` because dry-run paper-shadow cannot produce return-side
  evidence (Win Rate, expectancy, max drawdown). The recommended next
  human action — handled in its own future retro — is to flip
  `dry_run=False` to enter `paper_simulated` and collect those numbers.
- [`2026-05-17-freqai-linear-v1-promote-paper-simulated.md`](2026-05-17-freqai-linear-v1-promote-paper-simulated.md)
  — first ever `promote` retro for any source in this project.
  Authorizes `freqai_linear_v1` to flip
  `SourcePolicy(dry_run=False, position_pct_multiplier=0.2)` based on
  the 60-day, 595-signal v8 paper-shadow bundle. All ADR-007 §2.5
  gates pass: signal-side hold-out is stable Jan vs Feb, runtime
  hygiene is clean, multiplier stays at the paper_simulated cap, and
  no review blockers exist.
- [`2026-05-17-freqai-linear-v1-hold-paper-simulated.md`](2026-05-17-freqai-linear-v1-hold-paper-simulated.md)
  — first record of the same source operating at `paper_simulated`.
  Bundle `data/paper/20260517-053502Z-37b99b3f` (manifest fa344a55…)
  produced 545 orders, 545 fills (every one carrying `signal_id`),
  273 positions, no kill-switch fires, no data gaps, PnL +5.0076 USDT
  (+0.005%) over 60 days, Win Rate 55.5%, expectancy +0.019 USDT/trade,
  max drawdown -0.001%. Decision is `hold` because the next stage
  `testnet_canary` is hard-blocked by `phase_3_not_ready`; ADR-007 §2.5
  also requires a Phase 3 testnet runbook that does not yet exist.
