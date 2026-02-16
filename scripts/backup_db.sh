#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DB_FILE="$ROOT_DIR/backend/data/crypto_investor.db"
BACKUP_DIR="$ROOT_DIR/backend/data/backups"

if [ ! -f "$DB_FILE" ]; then
    echo "Database not found at $DB_FILE"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/crypto_investor_$TIMESTAMP.db"

echo "Backing up database..."
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

echo "Backup created: $BACKUP_FILE"

# Keep only the 7 most recent backups
cd "$BACKUP_DIR"
ls -t crypto_investor_*.db 2>/dev/null | tail -n +8 | xargs -r rm -f

REMAINING=$(ls -1 crypto_investor_*.db 2>/dev/null | wc -l)
echo "Backups retained: $REMAINING"
