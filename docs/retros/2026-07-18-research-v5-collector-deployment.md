# 2026-07-18 Research Protocol v5 collector deployment

- **Status**: deployed; timer active and enabled.
- **Deployment commit**:
  `d37d227874d49e88e8e8857f1bf45ea426ee7a3d`.
- **Fast-track report pushed first**: yes.
- **Signals/PnL**: none.
- **Trading effect**: none.

## Immutable deployment

The pushed fast-track result commit was transferred as Git bundle SHA-256
`6944f17b67bf2f90e3adf9469882b1194728cb9ef3dec2b2f66e2821e4d7a0a4`
and checked out detached and clean at
`/opt/nishiki-trader-v5-d37d227`. Existing v5 qualification checkouts were
left intact.

The dedicated ARM64 collector image is
`nishiki-research-v5:d37d227874d49e88e8e8857f1bf45ea426ee7a3d`, image ID
`sha256:7ad7f96146922078a141cc6e6c9fe92d1182e3f23767295570d40a375c6cdd8f`.
Its OCI revision label, internal `.collector-git-sha`, Compose environment, and
CLI expected commit all match the deployment commit. The image includes no
Nautilus runtime, signal generator, or order path.

The mode-0600 Compose environment is owned by the `nishiki` service user and
contains four non-secret lines: commit, data root, UID, and GID. Both the host
file and image environment have zero Binance/key/secret/token/password entries.

## Preflight and scheduling

A `--network none`, read-only, all-capabilities-dropped dry-run produced all
four BTC/ETH curve/BVOL plans and recorded:

```text
network_accessed=false
data_written=false
signals_generated=false
pnl_computed=false
credential_env_count=0
```

The rendered service uses
`WorkingDirectory=/opt/nishiki-trader-v5-d37d227`. Both unit files passed
systemd verification; unrelated pre-existing host-unit warnings did not refer
to either Nishiki unit. `nishiki-research-v5-collector.timer` is active and
enabled with runs at 04:15 UTC and 08:15 UTC. Its first scheduled run is
2026-07-18 04:15 UTC. No real collection was forced during deployment.

The pre-existing Protocol v2 timer remains active and enabled. The v5 data root
still contains the four qualification snapshots and four normalized Parquets,
with zero vintage conflicts and zero comparison-blocking markers. No v2 unit,
image, volume, checkout, or evidence was changed.

## Boundary audit

The timer can only invoke the credential-free append-preserving collector. One
failed stream does not prevent the other streams from being retained, but the
batch stays incomplete and nonzero. It cannot generate SignalEvent rows, run
Nautilus, compute PnL, call a promotion review, modify SourcePolicy, resume
testnet, or touch live orders. Both rejected v5 identities remain frozen and
the 2026-08..12 blind remains sealed.
