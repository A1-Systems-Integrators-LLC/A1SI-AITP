#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

echo "Generating secrets..."

DJANGO_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
FT_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
FT_API_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")

if [ -f "$ENV_FILE" ]; then
    echo "Updating existing .env file..."
    # Remove old keys if present
    sed -i '/^DJANGO_SECRET_KEY=/d' "$ENV_FILE"
    sed -i '/^FT_JWT_SECRET=/d' "$ENV_FILE"
    sed -i '/^FT_API_PASS=/d' "$ENV_FILE"
else
    echo "Creating new .env file..."
fi

cat >> "$ENV_FILE" << EOF
DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
FT_JWT_SECRET=$FT_JWT_SECRET
FT_API_PASS=$FT_API_PASS
EOF

chmod 600 "$ENV_FILE"

echo "Secrets written to $ENV_FILE (permissions set to 600)"
