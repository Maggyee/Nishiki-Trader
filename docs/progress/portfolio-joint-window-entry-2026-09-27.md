# Joint-window read-only entry staged

Date: 2026-09-27. `gateway_window_entry.py` is a checkout-only candidate for
an isolated-root, fixed-path `--check`. It reads a root-owned 0444 base
`helper_entry.py` through no-follow descriptors and checks its fixed SHA256
before executing the base verifier. That verifier supplies the held base
installation and the entry checks the held inventory adapter against its fixed
SHA256. The adapter requires a fixed root-owned 0600 joint manifest bound to
the base manifest and exactly six root-owned 0444 sources, now including the
entry's own installed bytes. The entry checks those bytes and closes custody.
All responses exit 2 with host qualification, activation history, source
authentication, caller coverage and network admission false. There is no
activation, installation, collection or permission interface.

The fixture tests stage actual source bytes and exercise checkout refusal,
fixed selection, incorrect pins, changed entry/source bytes and manifest
drift. The staged holder is test-only; neither it nor a root-owned file list
authenticates the running entry. A malicious or replaced startup file could
skip the checks. The host has no joint manifest or protected root entry; the
base four-file installation and historical v27 fixture manifest are unchanged.
The eight related joint-window test modules pass 93 tests; Ruff, formatting and
diff checks pass.

Before any host installation, separately review an independently protected
startup anchor and manifest binding, then establish continuous host exclusion,
mark and source ownership, complete host/container/proxy caller coverage and
fresh provider bounds. The isolated packet and timer tests do not prove a
425-second uninterrupted host blackout. No host rules changed, no venue
request was made and no live trading path or real collection was authorized.
