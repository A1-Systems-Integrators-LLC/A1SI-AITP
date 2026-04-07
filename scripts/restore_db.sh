#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$ROOT_DIR/backend/data/backups"
TEMP_DIR=""

cleanup() {
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

usage() {
    echo "Usage: $0 [BACKUP_FILE]"
    echo ""
    echo "Restore the PostgreSQL database from a backup file."
    echo "If no file is specified, the most recent backup is used."
    echo ""
    echo "Supported formats:"
    echo "  .sql.gz      Compressed backup"
    echo "  .sql.gz.gpg  Encrypted + compressed backup (requires BACKUP_ENCRYPTION_KEY)"
    exit 1
}

# Determine backup file
BACKUP_FILE="${1:-}"

if [ -n "$BACKUP_FILE" ]; then
    if [ ! -f "$BACKUP_FILE" ]; then
        echo "ERROR: Backup file not found: $BACKUP_FILE"
        exit 1
    fi
else
    # Auto-select newest backup
    if [ ! -d "$BACKUP_DIR" ]; then
        echo "ERROR: Backup directory not found: $BACKUP_DIR"
        exit 1
    fi

    # Try encrypted first, then compressed
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/a1si_aitp_*.sql.gz.gpg 2>/dev/null | head -1)
    if [ -z "$BACKUP_FILE" ]; then
        BACKUP_FILE=$(ls -t "$BACKUP_DIR"/a1si_aitp_*.sql.gz 2>/dev/null | head -1)
    fi

    if [ -z "$BACKUP_FILE" ]; then
        echo "ERROR: No backup files found in $BACKUP_DIR"
        exit 1
    fi

    echo "Auto-selected newest backup: $BACKUP_FILE"
fi

TEMP_DIR=$(mktemp -d)
WORK_FILE="$TEMP_DIR/restore.sql"

echo "Restoring from: $BACKUP_FILE"

# Step 1: Decrypt if encrypted
if [[ "$BACKUP_FILE" == *.gpg ]]; then
    if [ -z "${BACKUP_ENCRYPTION_KEY:-}" ]; then
        echo "ERROR: BACKUP_ENCRYPTION_KEY is required to decrypt .gpg backups"
        exit 1
    fi

    # Verify checksum if available
    CHECKSUM_FILE="${BACKUP_FILE}.sha256"
    if [ -f "$CHECKSUM_FILE" ]; then
        echo "Verifying SHA256 checksum..."
        if ! sha256sum -c "$CHECKSUM_FILE" --quiet 2>/dev/null; then
            echo "ERROR: Checksum verification failed!"
            exit 1
        fi
        echo "Checksum verified."
    fi

    echo "Decrypting..."
    DECRYPTED="$TEMP_DIR/backup.sql.gz"
    echo "$BACKUP_ENCRYPTION_KEY" | gpg --batch --yes --passphrase-fd 0 \
        --decrypt --output "$DECRYPTED" "$BACKUP_FILE"
    COMPRESSED="$DECRYPTED"
elif [[ "$BACKUP_FILE" == *.gz ]]; then
    COMPRESSED="$BACKUP_FILE"
else
    echo "ERROR: Unsupported file format. Expected .sql.gz or .sql.gz.gpg"
    exit 1
fi

# Step 2: Decompress
echo "Decompressing..."
gunzip -c "$COMPRESSED" > "$WORK_FILE"

DB_NAME="${POSTGRES_DB:-a1si_aitp}"
DB_USER="${POSTGRES_USER:-a1si}"

# Step 3: Create a pre-restore backup as safety net
echo "Creating pre-restore backup..."
docker compose exec -T postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$TEMP_DIR/pre-restore.sql.gz"

# Step 4: Restore
echo "Restoring database..."
docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" < "$WORK_FILE"

echo "Restore complete."
echo ""
echo "Next steps:"
echo "  1. Run 'make migrate' to apply any pending migrations"
echo "  2. Verify with 'python backend/manage.py check'"
