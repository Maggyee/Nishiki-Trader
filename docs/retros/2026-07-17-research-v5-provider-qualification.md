# 2026-07-17 Research Protocol v5 provider qualification

- **Status**: Passed locally and on the isolated cloud path.
- **Scope**: 2026-07-16 schema, lineage, publication lag, immutable archive,
  Spot catalog, and cloud collection only.
- **Pre-access commit**: `f8437f5e5f4cb942c50656ac3f466bf563fc90b3`.
- **Qualified collector commit**:
  `3d1687bd964eb138719b5a7a28f001d58afdaf11`.
- **PnL accessed**: no.
- **Trading effect**: none.

## Sequence and corrections

Protocol, provider contract, candidate fingerprints, implementation, synthetic
tests, and duplicated Nautilus integration were committed and pushed before the
first real response body. The initial July batch failed closed before snapshot
creation because official Futures/BVOL raw names differed from the synthetic
fixture. Schema-only correction `4891346` was pushed, then the same single day
passed locally. The detailed diagnosis is retained in
`docs/retros/2026-07-17-research-v5-schema-qualification-fix.md`.

The old v2 collector image then failed the first cloud preflight under
`--network none` because it intentionally lacks pandas. No request or file
write occurred. Dedicated runtime commit `3d1687b` added a minimal read-only
v5 image containing only numpy/pandas/pyarrow, the two collection modules, the
provider contract, and an immutable build-SHA marker. It contains no Nautilus
runtime, signal generator, or credential path.

## Local qualification

From clean commit `4891346`:

- all four BTC/ETH curve/BVOL snapshots passed official checksum, raw hash,
  UTC-day, contract-order, expiry, duplicate, finite-value, second-bucket,
  audit, envelope, and snapshot-hash validation;
- the second collection was idempotent for all four datasets, with zero new
  vintages and zero comparison-blocking markers;
- BTC/ETH Spot 1m imported 1,440 rows per asset for 2026-07-16; passive catalog
  audit found zero duplicate timestamps, missing intervals, or irregular
  steps, and the two timestamp sets were aligned;
- no demo signal or research SignalEvent was written.

Local and cloud content hashes match exactly:

| Dataset | Content SHA-256 |
|---|---|
| BTC delivery curve | `78dc54f989bcef9be89801f6d603740808925d8d6ff71271d982e98d4cf5d08e` |
| ETH delivery curve | `abc0499bec054ba9d1ba3154a682109e4448b810aca07e8df5b7ee7c6a35d71d` |
| BTC BVOL | `80cbf16501adfd0878ed7776632c6900d3dcf69a87119a116495dc12bdd56516` |
| ETH BVOL | `d45de93b7c6b65ecfaec3f0ce0f2e4657dda94f769dd515d748a3d964c44793f` |

## Cloud qualification

The exact commit was transferred as a Git bundle (SHA-256
`5d49a108bd7de8314831bc3ba4be7301867d61fa1477abd4a13c3456a06a55d1`)
to a separate detached checkout at `/opt/nishiki-trader-v5-3d1687b`. Existing
v2 code, image, timer, and evidence were not changed.

The dedicated ARM64 image is
`nishiki-research-v5:3d1687bd964eb138719b5a7a28f001d58afdaf11`, image ID
`sha256:1a1730370c2ecaa88981deff63fcd9dd9857d80b90c788b37ae70c4ef042a4fe`.
Its OCI revision label, internal build marker, environment, and CLI expected
commit all matched the qualified SHA. The `--network none` dry-run produced
four plans and left the evidence file count at zero.

The same Compose service later created four snapshots under the isolated
`/var/lib/nishiki-trader/research-v5` root. All four passed offline verification
inside a network-disabled read-only container. A second real collection was
idempotent for all four snapshots, with:

```text
snapshot_count=4
normalized_parquet_count=4
vintage_conflict_count=0
comparison_marker_count=0
credential_env_count=0
evidence_tree_sha256=401d59902aef4f9c7e86d8fe8003dd092a49a04ff55a3e56e8bd844bfe361744
```

Cloud snapshot envelope hashes differ from local envelopes only because
`retrieved_at` is part of the envelope; their immutable content hashes are
identical. Curve rows became available at the next UTC day boundary
(`2026-07-17T00:00:00Z`). BVOL rows were retrieved on 2026-07-17 and cannot
become eligible before `2026-07-18T00:00:00Z`, satisfying the forward
publication rule.

The v5 timer was not installed or enabled. Future daily collection remains
disabled until the protocol's fast-track reports are committed.

## Boundary audit and decision

No credentials, return, PnL, SignalEvent, SignalStore write, Nautilus
qualification run, SourcePolicy mutation, promotion review, testnet resume, or
live action occurred. The 2026-08..12 final blind remains unopened.

Provider/schema/lineage qualification is complete. The locked curve
2021-06..2022-12 and BVOL 2023-06..2025-12 historical fast-track inputs may now
be opened exactly once under Protocol v5. This permission does not allow
parameter changes, provider substitutions, PnL-selected ensembles, future
blind access, paper promotion, or timer activation.
