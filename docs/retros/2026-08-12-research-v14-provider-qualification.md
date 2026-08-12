# 2026-08-12 Protocol v14 Provider Qualification

- **Status**: blocked before metric values.
- **Development PnL**: unopened.
- **Confirmation and future blind**: sealed.
- **Trading effect**: none.

Protocol v14 was committed and pushed at `0ec5333` before its exact Coin
Metrics request was opened. The request returned HTTP 403 and no data rows:
`CapRealUSD` is unavailable with Community credentials. Community-scoped
catalog metadata also excludes `CapRealUSD`, `NVTAdj`, and `SOPR`; catalog-all
had shown product coverage rather than free-plan entitlement.

The 152-byte error body has SHA-256
`79bcb4a2c52a377337662b4e657df79b767d5cb9987e4e9ac8cb9855fb560489`.
No factor value, signal, Nautilus bundle, or PnL was produced. V14 is closed as
`blocked_provider_qualification`; it cannot be rescued by deleting the denied
metric, adding a paid credential, or substituting a different series under the
same identity.
