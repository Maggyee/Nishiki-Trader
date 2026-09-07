# Verification workflow template

Phase 5 offline Python and frontend checks. Integration databases and live
services are out of scope. The GitHub OAuth credential lacks `workflow` scope,
so `checks.yml` is retained here and is not active CI. Once a credential with
that scope is available, install it as `.github/workflows/checks.yml`.
