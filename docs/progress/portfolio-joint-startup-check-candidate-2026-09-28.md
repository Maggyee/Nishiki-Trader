# Joint-window protected startup check candidate

Date: 2026-09-28. `gateway_window_startup_check.py` is a separate, read-only
startup selection candidate. It must run with isolated system Python as root
from its fixed root-owned, single-link 0444 path under a protected `/run`
directory, with an independently selected base-manifest SHA256. It pins the
existing six installed joint source hashes directly in its code. The script
checks its own staged file metadata, reads and pins the installed entry under
protected ancestors, obtains the existing installed base verifier and held
six-source inventory, executes the selected entry's read-only check in its
own process, then rechecks the held sources and its own staged bytes. Every
result exits 2, keeps admission fields false and has no nft or network API.

An isolated mount/net/PID installation fixture stages the candidate at the
fixed root path after installing the reviewed base and six joint sources.
The correct selected base hash passes the read-only check; a wrong base hash,
weakened mode on the startup script, and a self-consistently reinventoried
installed source fail closed. The fixture also runs its earlier one-shot
activation, packet and post-write crash cases independently. Related tests
pass 106/106, with lint, formatting and diff checks clean. The fixture's
base-manifest selection is self-generated and is not the host's selected
base-manifest hash.

This candidate does not install or run on the host by merely existing in the
checkout. Its own expected SHA256 must be checked from a reviewed commit
before staging, and the host's original base-manifest hash must be selected
separately. Even a successful protected check attests only this one process's
read-only source selection; it cannot attest a different controller process,
continuous kernel coverage, mark/source ownership or provider-visible source.
No host blackout, grant, collector, venue request or trading operation is
authorized by this candidate.
