#!/bin/sh
# Act 3: SIGKILL the agent mid-ticket, restart it, and audit. Run from the repo root after demo_stage2.sh.
G() { .venv/bin/python -m govmem "$@"; }
TS=$(date -u +%H%M%S)
echo "=== uninterrupted baseline"
G ingest --seed-ticket D-3 --run-id act3-base-$TS | tail -1
echo "=== ACT 3: same ticket, the process is SIGKILLed after receipt 5"
GOVMEM_KILL_AFTER=5 G ingest --seed-ticket D-3 --run-id act3-$TS
echo "exit code $? (137 = killed by SIGKILL)"
echo "=== receipts that survived in Atlas"
G audit act3-$TS | tail -3
echo "=== RESTART: a new process resumes from the receipts"
G resume act3-$TS
echo "=== same steps as the uninterrupted run?"
G audit act3-base-$TS --compare act3-$TS | tail -3
