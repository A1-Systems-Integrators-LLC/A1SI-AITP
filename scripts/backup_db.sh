#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$ROOT_DIR/backend/data/backups"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_BASE="$BACKUP_DIR/a1si_aitp_$TIMESTAMP"

echo "Backing up PostgreSQL database..."
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-a1si}" "${POSTGRES_DB:-a1si_aitp}" | gzip > "${BACKUP_BASE}.sql.gz"

# Encrypt with GPG symmetric AES256 if BACKUP_ENCRYPTION_KEY is set
if [ -n "${BACKUP_ENCRYPTION_KEY:-}" ]; then
    if echo "$BACKUP_ENCRYPTION_KEY" | gpg --batch --yes --passphrase-fd 0 \
        --symmetric --cipher-algo AES256 \
        -o "${BACKUP_BASE}.sql.gz.gpg" "${BACKUP_BASE}.sql.gz"; then
        rm -f "${BACKUP_BASE}.sql.gz"
    else
        echo "ERROR: GPG encryption failed — keeping unencrypted backup"
        exit 1
    fi

    # SHA256 checksum
    sha256sum "${BACKUP_BASE}.sql.gz.gpg" > "${BACKUP_BASE}.sql.gz.gpg.sha256"
    echo "Encrypted backup: ${BACKUP_BASE}.sql.gz.gpg"
    echo "Checksum: ${BACKUP_BASE}.sql.gz.gpg.sha256"

    # Keep only the 7 most recent encrypted backups
    cd "$BACKUP_DIR"
    ls -t a1si_aitp_*.sql.gz.gpg 2>/dev/null | tail -n +8 | xargs -r rm -f
    ls -t a1si_aitp_*.sql.gz.gpg.sha256 2>/dev/null | tail -n +8 | xargs -r rm -f
    REMAINING=$(ls -1 a1si_aitp_*.sql.gz.gpg 2>/dev/null | wc -l)
else
    echo "WARNING: BACKUP_ENCRYPTION_KEY not set — backup is compressed but NOT encrypted."
    echo "Compressed backup: ${BACKUP_BASE}.sql.gz"

    # Keep only the 7 most recent compressed backups
    cd "$BACKUP_DIR"
    ls -t a1si_aitp_*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
    REMAINING=$(ls -1 a1si_aitp_*.sql.gz 2>/dev/null | wc -l)
fi

echo "Backups retained: $REMAINING"
