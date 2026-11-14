"""Failure test: kill a run and resume it from the receipts in the database.

Run: python -m govmem.killtest [--ticket D-3]
Writes only new receipts under run ids "kill-<HHMMSS>-...". Never touches seed data.
"""
import argparse
import copy
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from . import db, receipts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = re.compile(r"steps executed now: (\d+), steps replayed from receipts: (\d+)")


def run_id_prefix():
    return "kill-" + datetime.now(timezone.utc).strftime("%H%M%S")


def child_env(extra=None):
    env = dict(os.environ)
    for name in ("GOVMEM_KILL_AFTER", "GOVMEM_STEP_DELAY"):
        env.pop(name, None)
    if extra:
        env.update(extra)
    return env


def ingest(run_id, ticket, extra=None):
    return subprocess.run(
        [sys.executable, "-m", "govmem", "ingest", "--seed-ticket", ticket, "--run-id", run_id],
        cwd=ROOT, env=child_env(extra), capture_output=True, text=True)


def shape(docs):
    return [(d["kind"], d["tool"], d["digest"]) for d in docs]


def parse_counts(proc):
    found = LINE.findall(proc.stdout)
    return (int(found[-1][0]), int(found[-1][1])) if found else None


def check_resume(run_id, before, baseline, k):
    """Resume a killed run and check it against the uninterrupted baseline."""
    B, base_tools, base_shape, ticket = baseline
    proc = ingest(run_id, ticket)
    docs = receipts.load(run_id)
    counts = parse_counts(proc)
    ok, _ = receipts.verify(run_id)
    seqs = [d["seq"] for d in docs]
    tools = sum(1 for d in docs if d["kind"] == "tool")
    same = shape(docs) == base_shape
    unchanged = [d["hash"] for d in docs[:k]] == [d["hash"] for d in before]
    repeated = 0 if seqs == list(range(1, B + 1)) else len(seqs) - len(set(seqs))
    counts_ok = counts == (B - k, k)
    passed = (proc.returncode == 0 and len(docs) == B and tools == base_tools
              and unchanged and counts_ok and ok and same and repeated == 0)
    return {"k": k, "before": len(before), "executed": counts[0] if counts else -1,
            "replayed": counts[1] if counts else -1, "tools": tools, "repeated": repeated,
            "chain": ok, "same": same, "pass": passed, "proc": proc, "docs": docs}


def tamper(base_docs, run_id):
    """Attack an in-memory copy. Nothing here is written back."""
    results = []

    altered = copy.deepcopy(base_docs)
    altered[1]["result"] = {"tampered": True}
    ok, message = receipts.verify_chain(altered, run_id)
    results.append(("alter seq %d result" % altered[1]["seq"],
                    (not ok) and ("seq %d" % altered[1]["seq"]) in message, message))

    removed = copy.deepcopy(base_docs)
    del removed[len(removed) // 2]
    ok, message = receipts.verify_chain(removed, run_id)
    results.append(("remove middle receipt", not ok, message))

    swapped = copy.deepcopy(base_docs)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    ok, message = receipts.verify_chain(swapped, run_id)
    results.append(("swap two receipts", not ok, message))

    dropped = copy.deepcopy(base_docs[:-1])
    ok, _ = receipts.verify_chain(dropped, run_id)
    caught = ok and receipts.tail_state(dropped) == "open" and receipts.tail_state(base_docs) == "complete"
    results.append(("drop tail stays verifiable", caught,
                    "tail %s (full baseline %s)" % (receipts.tail_state(dropped), receipts.tail_state(base_docs))))
    return results


def main():
    parser = argparse.ArgumentParser(description="Kill-and-resume failure test")
    parser.add_argument("--ticket", default="D-3")
    args = parser.parse_args()
    prefix = run_id_prefix()

    base_id = prefix + "-base"
    proc = ingest(base_id, args.ticket)
    base_docs = receipts.load(base_id)
    base_ok, base_message = receipts.verify(base_id)
    if proc.returncode != 0 or not base_ok:
        print("BASELINE FAILED: returncode %s, %s" % (proc.returncode, base_message))
        print(proc.stdout[-400:])
        print(proc.stderr[-400:])
        return 1
    B = len(base_docs)
    T = sum(1 for d in base_docs if d["kind"] == "tool")
    baseline = (B, T, shape(base_docs), args.ticket)

    rows = []
    for k in range(1, B):
        run_id = "%s-k%d" % (prefix, k)
        killed = ingest(run_id, args.ticket, {"GOVMEM_KILL_AFTER": str(k)})
        before = receipts.load(run_id)
        if killed.returncode != -9 or [d["seq"] for d in before] != list(range(1, k + 1)):
            rows.append({"k": k, "before": len(before), "executed": -1, "replayed": -1,
                         "tools": -1, "repeated": -1, "chain": False, "same": False, "pass": False,
                         "proc": killed, "docs": before})
            continue
        rows.append(check_resume(run_id, before, baseline, k))

    ext_id = prefix + "-ext"
    proc = subprocess.Popen(
        [sys.executable, "-m", "govmem", "ingest", "--seed-ticket", args.ticket, "--run-id", ext_id],
        cwd=ROOT, env=child_env({"GOVMEM_STEP_DELAY": "0.5"}), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.time() + 120
    while db.runs().count_documents({"run_id": ext_id}) < 3 and time.time() < deadline:
        time.sleep(0.1)
    proc.kill()
    proc.wait()
    ext_before = receipts.load(ext_id)
    m = len(ext_before)
    if proc.returncode == -9 and 0 < m < B:
        ext = check_resume(ext_id, ext_before, baseline, m)
    else:
        ext = {"k": m, "pass": False, "proc": proc}

    tampers = tamper(base_docs, base_id)

    print("k  before  executed  replayed  tools  repeated  chain  sequence  result")
    for row in rows:
        print("%-2d %-7d %-9d %-9d %-6d %-9d %-6s %-9s %s" % (
            row["k"], row["before"], row["executed"], row["replayed"], row["tools"], row["repeated"],
            "ok" if row["chain"] else "BROKEN", "same" if row["same"] else "DIFFERS",
            "PASS" if row["pass"] else "FAIL"))
    print("BASELINE: %d receipts, %d tool calls" % (B, T))
    passed = sum(1 for row in rows if row["pass"])
    print("KILL MATRIX: %d of %d kill points passed" % (passed, len(rows)))
    print("EXTERNAL KILL: %s (killed at %d receipts)" % ("PASS" if ext["pass"] else "FAIL", m))
    print("TAMPER: %d of %d detected as expected" % (sum(1 for _, hit, _ in tampers if hit), len(tampers)))
    for label, hit, message in tampers:
        print("  %s: %s (%s)" % (label, "caught" if hit else "MISSED", message))
    for row in rows:
        if not row["pass"]:
            print("--- failing k=%d ---\n%s%s" % (row["k"], row["proc"].stdout[-500:], row["proc"].stderr[-500:]))
    if not ext["pass"]:
        print("--- external kill failed ---\n%s" % getattr(ext["proc"], "stdout", ""))
    return 0 if passed == len(rows) and ext["pass"] and all(hit for _, hit, _ in tampers) else 1


if __name__ == "__main__":
    sys.exit(main())
