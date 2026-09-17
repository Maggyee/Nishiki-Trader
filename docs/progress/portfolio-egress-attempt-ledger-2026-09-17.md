# Prospective local egress attempt accounting

Date: 2026-09-17. Offline implementation and synthetic acceptance only.

The [held local custody binding](portfolio-local-authority-binding-2026-09-16.md)
now has a prospective accounting consumer. The new project-owned
`apps/strategies_nautilus/portfolio_egress_ledger.py` persists preparation records,
checks a borrowed binding before and after persistence, and retains attempted work
when results fail or become uncertain. This completes the local bookkeeping part
of the prior next step; complete all-caller accounting and gateway enforcement
remain unimplemented. No venue request, credential read, host rule change, service
change or additional maintenance window occurred.

## Persistence and failure behavior

Each private, owned 0700 root can create its fixed `local-egress-attempts-v1`
directory only once. Creation consumes that local scope even if initialization
later fails. The component uses the existing bounded hash-chained `_Journal`,
fsyncs each record and reserves space for an incident. It never reopens or resumes
a consumed directory. Choosing another root creates an independent local fixture;
this is not an installed global authorization or anti-rollback boundary.

Only one preparation may be pending. Preparation records use fixed operation
costs rather than caller-selected amounts. REST exchangeInfo records weight 20 /
RAW_REQUESTS 1; account connect and subscription each record documented weight 2;
market connect retains an unknown charge. Account/market connections are counted
separately from raw REST calls. Caller labels include collector, host, container,
Tailscale and proxy but **are not authenticated process identities**. These are
prepared-operation counts, not proof that any request reached a provider or even
that a corresponding caller exists. Success/failure results are local inputs.

The binding's `verify()` brackets preparation persistence. A changed selected
binding stops further preparation, including when the change is observed after a
preparation was fsynced: that attempt stays uncertain. Outcome recording and local
checkpoints also verify the binding. Held archive descriptors, original byte
prefix, inode, link count, ownership and permissions detect observed storage
changes. A process owner check prevents a fork from using or closing its parent's
writer; a lock serializes concurrent access. A competing pending preparation fails
and halts the ledger rather than issuing another receipt.

Wall and monotonic clocks must remain nondecreasing and their cumulative offset
change within 50 ms. This is a local discontinuity detector, not a provider-clock
qualification. Detected failures attempt to append an open-ended gap from the last
successful observation using the last accepted timestamp; the offending clock
value is not accepted as trustworthy time. Incident reasons retain exception types
only. Storage failure can prevent the gap record itself from being written; replay
then reports the incomplete prefix, never a recovered permission. SIGKILL after
preparation leaves a pending uncertain attempt. Failed and uncertain outcomes end
the ledger and never refund preparations. Close can retain pending uncertainty.

The preexisting journal truncates a failed, unacknowledged final write when
possible. A failed outcome fsync therefore retains the prior uncertain preparation.
If truncation also fails, the archive is ambiguous and must not be selected as
qualified persistence evidence. This work tests process crashes and injected fsync
failures; it does not establish power-loss, storage rollback or malicious-root
resistance. The component borrows its binding and does not own or close it.

## Offline replay and scope

`apps.ops.portfolio_egress_ledger` reads only private bounded files, requires the
original archive SHA256 and selected binding SHA256, validates canonical bytes,
chain, clock and semantic transitions, and exclusively writes a new private report.
It never reconstructs a binding object or opens the ledger for writing.

```bash
.venv/bin/python -m apps.ops.portfolio_egress_ledger \
  --archive data/egress-attempt-ledger-2026-09-17/local-egress-attempts-v1/events.jsonl \
  --archive-sha256 65ddb811a125f21e657bc5e8f72796848cb60ee66ac04f94e245abc5dbd3ee46 \
  --binding-sha256 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --report /PRIVATE-DIRECTORY/new-replay.json
```

Exit 2 means a blocked report was written; exit 1 means refusal. Optional
`--start-monotonic-ns` / `--through-monotonic-ns` must be supplied together.
Both interval edges are inclusive. Counts apply to preparation timestamps within
the local interval, with their latest archived outcomes; they are neither provider
buckets nor as-of-time outcome snapshots. `recorded_attempts` counts the entire
archive. Empty intervals do not imply zero usage. Known documented weight excludes
explicitly counted unknown-charge operations, and is not a complete total charge.

Repeated unchanged rule observations cannot prove that no traffic was missed
between polls. Every report therefore retains unknown total/other-caller upper
bounds and false complete coverage, authenticated caller labels, future enforcement,
restart, network and trading admission. History before start and after the last
observation is unavailable; an explicit incident gap adds to, not replaces, these
permanent sampling limitations. No production transport consumes preparation
receipts, and `network_admitted` is always false even on successful preparation.

## Acceptance

**40 new / 239 focused Python tests pass.** Coverage includes mixed caller labels
and REST/account/market costs, unknown charges, inclusive/empty intervals,
failed/uncertain/closed-pending attempts, permanent drift refusal before/after
persistence, clock discontinuity, replaced/corrupt/missing/hardlinked/symlinked
archives, mode changes, descriptor cleanup, initialization failure, failed
preparation/outcome fsync, archive incident reserve, concurrency, fork ownership,
SIGKILL, canonical/hash/chain/semantic corruption and exclusive CLI output.
Integration tests use the actual `AuthorityBinding` implementation on protected
fixture files and mocked local network observations: source bytes or a source-route
change close the binding and prevent a success outcome. This is not a new actual
host observation. Core fixture tests explicitly prohibit socket/DNS access.

A separate retained synthetic run records five preparations: four successful and
one uncertain after deliberately changed binding. Across those records the known
weight subtotal is 44, raw requests 2, connection attempts 2, plus one unknown
market-connect charge. The final status is `gap`. Two fresh CLI processes return 2
and produce byte-identical reports, SHA256
`4fa2e027ced6e275fd84249c3ccf282e29738a900c9426b2e025711fd46d3a5d`.
The synthetic source script, archive and reports are under
`data/egress-attempt-ledger-2026-09-17/`, with exact pins in the
[result JSON](portfolio-egress-attempt-ledger-2026-09-17.json). They do not represent
actual shared-IP calls or authenticate any gateway/source authority.

Focused regression includes the ledger, TLS provenance persistence, joint
reservations, joint admission, authority binding and installation suites. Ruff,
format, local links, original/frozen evidence pins and diff checks pass. The full
application suite and unchanged kernel harnesses were not rerun. Project status,
reading index and module READMEs are updated; upstream sources and live trading
paths are untouched.

Next integrate this bookkeeping with the **isolated controlled gateway**: ensure
sending cannot bypass durable preparation, authenticate caller identities or block
unrecorded traffic, and test drift/revocation races with local peers. That work must
establish continuous coverage and bounded future enforcement before it can support
actual shared-IP usage bounds. Fresh rate/clock evidence, provider charge resolution
and explicit source/gateway authority policy remain required before a separately
reviewed real network scope. The consumed bootstrap stays consumed; the joint
contract remains 17 GETs / 468 documented weight, network/trading blocked, strict
continuity 0/14. No second IPv4 is needed or proposed by this increment.
