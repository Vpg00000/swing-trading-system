#!/usr/bin/env bash
# scripts/db_backup.sh - Automated Database Auto-Backup cron script (T-311)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DB_FILE="${PROJECT_ROOT}/data/system.db"
BACKUP_DIR="${PROJECT_ROOT}/data/backups"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
BACKUP_FILE="${BACKUP_DIR}/system_backup_${TIMESTAMP}.db"
MAX_BACKUPS=30

mkdir -p "${BACKUP_DIR}"

echo "[$(date +"%Y-%m-%d %H:%M:%S")] Starting automated database backup..."

if [ ! -f "${DB_FILE}" ]; then
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] WARNING: Database file ${DB_FILE} not found. Creating empty database file for backup."
    mkdir -p "$(dirname "${DB_FILE}")"
    touch "${DB_FILE}"
fi

# Perform safe online SQLite backup if sqlite3 is installed, else use standard cp
if command -v sqlite3 &> /dev/null; then
    sqlite3 "${DB_FILE}" ".backup '${BACKUP_FILE}'"
else
    cp "${DB_FILE}" "${BACKUP_FILE}"
fi

# Compress backup file
gzip -f "${BACKUP_FILE}"
BACKUP_GZ="${BACKUP_FILE}.gz"

echo "[$(date +"%Y-%m-%d %H:%M:%S")] SUCCESS: Database backup created at ${BACKUP_GZ}"

# Prune old backups, keeping only the last MAX_BACKUPS
BACKUP_COUNT=$(ls -1t "${BACKUP_DIR}"/system_backup_*.db.gz 2>/dev/null | wc -l)
if [ "${BACKUP_COUNT}" -gt "${MAX_BACKUPS}" ]; then
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] Pruning old backups (keeping latest ${MAX_BACKUPS})..."
    ls -1t "${BACKUP_DIR}"/system_backup_*.db.gz | tail -n +"$((MAX_BACKUPS + 1))" | xargs rm -f
fi

echo "[$(date +"%Y-%m-%d %H:%M:%S")] Backup process completed successfully."
