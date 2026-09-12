#!/bin/sh
set -eu

data_dir="${DATA_DIR:-/app/data}"
key_file="$data_dir/.credential-encryption-key"
runtime_key="${CREDENTIAL_ENCRYPTION_KEY:-${ENCRYPTION_KEY:-}}"

mkdir -p "$data_dir"

if [ -z "$runtime_key" ]; then
    if [ -s "$key_file" ]; then
        runtime_key="$(cat "$key_file")"
    else
        umask 077
        runtime_key="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
        printf '%s\n' "$runtime_key" > "$key_file"
    fi
fi

export ENCRYPTION_KEY="$runtime_key"
export CREDENTIAL_ENCRYPTION_KEY="$runtime_key"

alembic upgrade head
exec uvicorn src.api.app:app --host 0.0.0.0 --port 8000
