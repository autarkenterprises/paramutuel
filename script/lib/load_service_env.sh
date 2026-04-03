#!/usr/bin/env bash
# Loads environment variables for local service orchestration into the *current*
# shell session (must be sourced, not executed).
#
# Usage (from repo root):
#   source script/lib/load_service_env.sh
#
# Defaults:
#   SERVICE_ENV_FILE: config/service.env
#   SERVICE_ENV_EXAMPLE_FILE: config/service.env.example
#
# shellcheck shell=bash

if [[ "${BASH_SOURCE[0]:-$0}" == "$0" ]]; then
  echo "error: source this file (do not execute):  source script/lib/load_service_env.sh" >&2
  exit 1
fi

set -euo pipefail

ENV_FILE="${SERVICE_ENV_FILE:-config/service.env}"
EXAMPLE_FILE="${SERVICE_ENV_EXAMPLE_FILE:-config/service.env.example}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  return 0
fi

# Backwards compatibility: if an existing root `.env` exists, allow using it.
if [[ -f ".env" ]]; then
  echo "warning: '$ENV_FILE' not found; falling back to '.env'." >&2
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
  return 0
fi

if [[ -f "$EXAMPLE_FILE" ]]; then
  echo "error: missing '$ENV_FILE'. Copy from '$EXAMPLE_FILE' and edit values." >&2
  return 1
fi

echo "error: neither '$ENV_FILE' nor '$EXAMPLE_FILE' exists." >&2
return 1
