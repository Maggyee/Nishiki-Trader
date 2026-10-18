# Retros

Signed ADR-007 §2.6 `SourcePolicy` decision records. Every change to a
`(source, model_version)` policy, including an explicit decision not to
change it, needs one here.

- **Current phase**: 3 runtime built, canary paused. Only the
  `freqai_linear_v1 / linear-mom-train20240105` chain is kept; its newest
  record (2026-07-29 demote to `paper_simulated`) is the current decision.
- **Boundaries**: records are generated, not hand-written, and never edited
  after signing. `testnet_runner` scans this directory at startup and treats
  the newest `decision_allowed` record per source/model as authoritative; a
  demote or disable keeps the canary closed.
- **Next entrypoint**: generate a new record with
  `uv run python -m apps.strategies_nautilus.runners.promotion_review --help`
  and `--output-markdown docs/retros/<UTC date>-<source>-<model>-<decision>-<target_stage>.md`.
- **Archived**: the 175 research-protocol retros (v2–v53) are in tag
  `archive/pre-slim-2026-10-17`; conclusions are in `docs/research/README.md`.
