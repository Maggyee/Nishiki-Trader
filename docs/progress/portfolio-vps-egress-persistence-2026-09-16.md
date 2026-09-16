# Fixed-scope egress journal and crash replay — 2026-09-16

The isolated egress controller now has an offline disk-backed scope profile.
`PersistentFixtureGuard` persists activation before dispatch and refuses every
reopen of the fixed scope, including after failed initialization or an abrupt
process exit. Read-only replay retains recorded preparations and uncertain sends.
**65 focused Python tests and 56 Linux namespace checks pass.** No host guard,
service, venue request or real collection is enabled.

## Storage and failure behavior

The existing controller's four-attempt bound, serialized dispatch/revocation,
sender privilege separation and TTL fallback remain intact. The new subclass
claims `fixture-scope-v1` beneath a pre-existing caller-selected storage root.
The root must be owned by the current user and mode 0700. Atomic exclusive
`mkdir` elects one initializer; the directory's existence permanently consumes
the scope in that root. No alternate journal filename, reopen, reset, refund or
resume method exists.

Before any transport callback, it fsyncs the root containing the scope marker,
creates the exclusive mode-0600 journal, fsyncs the scope directory containing
that journal, and writes/fsyncs `activated`. Each preparation and result uses the
existing serialized write/fsync mechanism. A startup failure closes descriptors
but retains the scope marker. Startup itself grants no kernel permission and
sends no request. A refused second initializer also grants/revokes nothing; it
cannot become another controller or disrupt the current owner's lease.

Active checks compare root/scope inode identity, owner and permissions and reject
journal permission changes or extra hard links, in addition to the original
exact-byte/inode checks. Observed failures halt dispatch and attempt revocation
even when journal writing fails. A controller crash still leaves permission until
the kernel timeout; persistence does not provide immediate death-triggered
revocation. There is no recovery transport callback or restarted lease grant.

`review_fixture_journal` takes selected raw bytes, their expected SHA256 and the
selected fixture identity. It validates exact canonical records, hash links,
monotonic clocks, attempt numbers and lifecycle ordering. It accepts a complete
record prefix ending during an uncertain attempt, reports that uncertainty even
after recorded revocation, and rejects malformed/partial records and invalid
transitions. It always returns false for restart, capture and gateway coverage.
An empty/missing journal after interrupted initialization cannot be reviewed;
the existing directory still blocks another initializer.

## Acceptance

The 25 additional Python cases cover:

- Root/scope/journal fsync ordering before the first transport callback; failures
  at each of the three startup sync points leave the scope consumed without sends.
- Two concurrent initializers elect exactly one owner. Public/symlink storage
  roots are refused; replaced roots/scopes, permission changes and extra journal
  links halt and revoke before transport.
- Abrupt process exit after scope creation, activation, preparation, a successful
  result and terminal revocation. System Python 3.10 processes use the host's
  ext4-backed temporary directory. For each available journal, two separate new
  interpreters produce identical reports; another interpreter refuses reopening
  and preserves the original bytes. The scope-only crash retains no journal.
- Selected-hash/identity mismatch, partial JSON, rehashed invalid transitions,
  duplicate activation, backward clocks, invalid attempts, sends after revocation,
  and uncertain-attempt preservation through shutdown.

Four additional actual Linux checks join this backend to the existing isolated
controller: a local echo dispatch, terminal replay, unchanged-byte restart refusal,
and kernel-counted denial of the raw sender after revocation. These use the
harness's private tmpfs, distinct from the ext4 process-crash tests. The original
52 kernel checks still pass, including the deliberately unclosed privileged-rule
mutation race and crash-to-TTL-expiry fallback.

Commands run from the repository root:

```bash
uv run pytest -q tests/ops/test_egress_guard_selftest.py
uv run ruff check infra/egress-guard/selftest.py tests/ops/test_egress_guard_selftest.py
uv run ruff format --check infra/egress-guard/selftest.py tests/ops/test_egress_guard_selftest.py
/usr/bin/python3 -I infra/egress-guard/selftest.py
```

Local documentation links, `git diff --check` and the unchanged frozen capture
contract hash also pass. The prior full application regression was not rerun:
this change is confined to the standalone infrastructure fixture and its tests.
The final namespace-tested script SHA256 is
`f7e2d11258e100b097298d15b5a278b91649e27695b9670b57a4f558ffb94630`.

## Limits and next entrypoint

This verifies process-exit persistence and OS fsync ordering, not host power-loss,
VM restart, filesystem corruption, backup rollback or controller redeployment.
The root is caller-selected, not a globally authenticated scope registry. A
privileged operator can choose a different root or delete/replace its marker;
the profile cannot establish global single-use authority against that behavior.
Storage administration and intermediate path components remain trusted.
Observed-now hashes bind selected bytes, not historical authorship or completeness:
a caller-rehashed valid prefix cannot prove later records were never lost.
Replay therefore reports **recorded** preparations, never an authoritative
remaining provider budget or permission to send.

Next bind an actual source and authorized callers to the controller, qualify a
fixed deployment storage root and crash/revocation handling, and obtain the missing
first-request evidence or define a separate prospective bootstrap contract.
No real source, complete all-caller ledger or provider quota reservation exists.
The frozen 17-GET / 468-documented-weight draft hash remains
`91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48`.
Consumed ADR-017/public-depth scopes remain consumed, full-account/UTC/flow/reset
qualification remains blocked, and strict continuity stays **0/14**.

Changed files: `infra/egress-guard/selftest.py`, its README,
`tests/ops/test_egress_guard_selftest.py`, this report,
`docs/agent-reading-list.md` and `docs/project-status.md`. No upstream source or
live trading path was touched. The status dashboard and reading index now identify
this acceptance and the remaining deployment/source/bootstrap work.
