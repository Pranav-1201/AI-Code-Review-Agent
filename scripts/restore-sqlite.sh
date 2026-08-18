#!/bin/sh
# ==========================================================
# Phase F — restore the scan store from a snapshot.
#
# Run this from the repository root ON THE HOST, with the stack stopped:
#
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml down
#   ./scripts/restore-sqlite.sh /var/lib/acra-backups/scan-20260819T000000Z.db
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
#
# This is NOT the inverse of backup-sqlite.sh. Two things make it different:
#   1. Writers must be stopped first. Replacing the file under a live worker
#      gives you a corrupt database and a confusing incident.
#   2. The -wal and -shm sidecars MUST be removed. Leaving them beside a
#      restored main file is how a "successful" restore silently resurrects
#      pre-restore data: SQLite replays the stale WAL on next open.
# ==========================================================
set -eu

SNAPSHOT="${1:-}"

# The default points into the Docker named volume. Compose prefixes volume
# names with the project name, which defaults to the directory name — so this
# is a good guess and not a guarantee. `docker volume inspect` is authoritative.
DB_PATH="${DB_PATH:-/var/lib/docker/volumes/etproject_scan-data/_data/scan_states.db}"

if [ -z "$SNAPSHOT" ]; then
	echo "usage: $0 <snapshot.db>" >&2
	echo "" >&2
	echo "DB_PATH may be overridden; it currently points at:" >&2
	echo "  $DB_PATH" >&2
	echo "" >&2
	echo "Confirm the real path with:" >&2
	echo "  docker volume inspect \$(docker volume ls -q | grep scan-data)" >&2
	exit 2
fi

if [ ! -f "$SNAPSHOT" ]; then
	echo "no such snapshot: $SNAPSHOT" >&2
	exit 1
fi

# Refuse to restore a file SQLite cannot read, rather than replacing a good
# database with a broken one and discovering it at the next scan.
if ! sqlite3 "$SNAPSHOT" "pragma integrity_check;" | head -1 | grep -qx "ok"; then
	echo "snapshot failed integrity_check; refusing to restore: $SNAPSHOT" >&2
	exit 1
fi

# Refuse to write somewhere that does not exist yet. Creating the path here
# would usually mean the volume is not mounted where this script thinks, and
# the restore would appear to succeed while the stack kept using the old data.
db_dir="$(dirname "$DB_PATH")"
if [ ! -d "$db_dir" ]; then
	echo "target directory does not exist: $db_dir" >&2
	echo "the volume is probably mounted elsewhere; set DB_PATH explicitly" >&2
	exit 1
fi

echo "restoring $SNAPSHOT -> $DB_PATH"

if [ -f "$DB_PATH" ]; then
	aside="$DB_PATH.pre-restore-$(date -u +%Y%m%dT%H%M%SZ)"
	mv "$DB_PATH" "$aside"
	echo "previous database moved aside: $aside"
fi

cp "$SNAPSHOT" "$DB_PATH"

# The sidecars belong to the database that was just moved aside, not to the
# one just restored. See the header comment.
rm -f "$DB_PATH-wal" "$DB_PATH-shm"

echo "done. Start the stack and confirm GET /api/health responds."
