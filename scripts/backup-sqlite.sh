#!/bin/sh
# ==========================================================
# Phase F — periodic snapshot of the scan store.
#
# Uses sqlite3 ".backup", NEVER `cp`. The store runs in WAL mode, so copying
# the .db file while a writer is active captures a torn state: committed data
# may still live in the -wal sidecar and not yet in the main file. ".backup"
# uses SQLite's online backup API and produces a consistent single-file
# snapshot regardless of concurrent writes.
# ==========================================================
set -eu

DB_PATH="${DB_PATH:-/data/scan_states.db}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"

log() {
	# One line, timestamped, greppable. Not JSON: this runs in a stock alpine
	# container with no Python, and hand-rolling a second JSON emitter here
	# would be worse than a plain line.
	echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) backup: $*"
}

mkdir -p "$BACKUP_DIR"

log "started; db=$DB_PATH dir=$BACKUP_DIR interval=${BACKUP_INTERVAL_SECONDS}s keep=$BACKUP_KEEP"

while true; do
	if [ ! -f "$DB_PATH" ]; then
		# Not an error: the store is created lazily on the first scan, so an
		# untouched deployment legitimately has no database yet.
		log "no database at $DB_PATH yet; skipping this cycle"
	else
		dest="$BACKUP_DIR/scan-$(date -u +%Y%m%dT%H%M%SZ).db"

		# A failed backup must NOT kill the loop. A service that exits on one
		# bad night stops protecting every subsequent night, which is strictly
		# worse than a noisy log. `set -e` would do exactly that, so the
		# failure is handled explicitly here.
		if sqlite3 "$DB_PATH" ".backup '$dest'"; then
			log "wrote $dest ($(wc -c <"$dest") bytes)"

			# Rotation: keep the newest $BACKUP_KEEP, delete the rest. Sorted
			# by name, which is chronological because the timestamp is a
			# zero-padded UTC basic-format string.
			ls -1 "$BACKUP_DIR"/scan-*.db 2>/dev/null \
				| sort -r \
				| tail -n +"$((BACKUP_KEEP + 1))" \
				| while read -r old; do
					rm -f "$old" && log "rotated out $old"
				done
		else
			log "ERROR backup failed; leaving previous snapshots in place"
			# A partial file is worse than none: rotation sorts by name, so a
			# truncated newest snapshot would push a good one out of the window.
			rm -f "$dest"
		fi
	fi

	sleep "$BACKUP_INTERVAL_SECONDS"
done
