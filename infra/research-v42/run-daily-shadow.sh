#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/home/orca/orca/projects/trader"
cd "${REPO_ROOT}"

exec "${REPO_ROOT}/.venv/bin/python" -m apps.ops.research_v42_shadow_daily
