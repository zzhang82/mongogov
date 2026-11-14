#!/bin/sh
# Stage 3 evidence: Act 2b (veto), isolation beat, revise and forget. Run from the repo root after demo_stage2.sh.
G() { .venv/bin/python -m govmem "$@"; }
TS=$(date -u +%H%M%S)
date -u +"%Y-%m-%dT%H:%M:%SZ"
echo "=== ACT 2b: lookalike ticket D-3 (same symptoms as TR-108, different cause)"
G ingest --seed-ticket D-3 --run-id s3-act2b-$TS
echo "=== AUDIT: the veto is a receipt"
G audit s3-act2b-$TS
echo "=== ISOLATION: the Act 2a ticket text under team-billing"
G ingest --seed-ticket D-2 --team team-billing --id D-2-as-billing --run-id s3-isolation-$TS
echo "=== G5 REVISE: propose a corrected version of mem-TR-201 (team-billing)"
G memories --team team-billing --all
G revise mem-TR-201 --as lin.wu --title "Refund the duplicate charge and check proration" --step "Open the billing timeline and find the two charges for the plan change." --step "Refund the duplicate charge." --step "Check that the proration credit was applied, then send the refund receipt."
echo "--- before promotion: the old version is still the one active version"
G memories --team team-billing --all
echo "--- the proposer cannot approve the revision"
G review promote rev-mem-TR-201-v2 --as lin.wu || echo "exit code $?"
G review promote rev-mem-TR-201-v2 --as omar.haddad
G memories --team team-billing --all
echo "=== G5 FORGET: retire mem-TR-202"
G forget mem-TR-202 --as omar.haddad --reason "Tax details moved to the billing portal; fix no longer applies"
G memories --team team-billing --all
echo "--- a retired memory cannot come back"
G forget mem-TR-202 --as omar.haddad --reason "again" || echo "exit code $?"
echo "=== governance receipts"
G audit governance | tail -8
