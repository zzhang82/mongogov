"""Pre-registered metric definitions:
- Unit: one ticket run. Classes are the ticket's "kind" field (twin, lookalike; for the demo file: novel, repeat, lookalike). Results are reported per class, never blended across classes.
- tool_calls: number of receipts with kind "tool" for the run, read from the runs collection.
- resolved: the run's "final" receipt has a non-null result.fix_id (the applied fix passed verify_fix).
- wrong_fixes: length of result.wrong_fixes in the final receipt (a fix applied whose verify failed).
- vetoed: 1 when the run has a receipt with tool "veto".
- held: final result.status == "held".
- path: final result.path (fast, trusted, catalog).
- Conditions: "empty" = the same tickets run for a team namespace that has no memories; "trained" = the tickets run for their own team with the current memory. Same harness, same thresholds, same tool pipeline for both.
- Each condition is run twice (rep a and rep b). Any difference in tool_calls or step sequence between reps is reported, not averaged away.
- No wall-clock time is measured or reported.
"""
import argparse
import datetime
import json
from pathlib import Path

from . import agent, config, db, receipts, seed

EMPTY_TEAM = "team-empty-baseline"


def clean_scratch():
    db.memories().delete_many({"namespace": EMPTY_TEAM})
    db.reviews().delete_many({"namespace": EMPTY_TEAM})
    db.tickets().delete_many({"team": EMPTY_TEAM})


def get_memory_counts():
    counts = {}
    for doc in db.memories().aggregate([{"$group": {"_id": {"ns": "$namespace", "lc": "$lifecycle"}, "c": {"$sum": 1}}}]):
        counts.setdefault(doc["_id"]["ns"], {})[doc["_id"]["lc"]] = doc["c"]
    return counts


def run_one(ticket, condition, rep, stamp):
    tid = ticket["id"]
    run_id = f"eval-{stamp}-{condition}-{rep}-{tid}"
    agent.run_ticket(ticket, run_id=run_id, out=lambda *a: None)
    stored = receipts.load(run_id)
    chain_ok, _ = receipts.verify(run_id)
    final = next((d["result"] for d in stored if d.get("tool") == "final"), {})
    tool_calls = sum(1 for d in stored if d.get("kind") == "tool")
    return {
        "run_id": run_id, "condition": condition, "rep": rep, "ticket": tid,
        "kind": ticket["kind"], "path": final.get("path"), "tool_calls": tool_calls,
        "resolved": final.get("fix_id") is not None,
        "wrong_fixes": len(final.get("wrong_fixes") or []),
        "vetoed": 1 if any(d.get("tool") == "veto" for d in stored) else 0,
        "held": final.get("status") == "held", "chain_ok": chain_ok,
        "sequence": [(d.get("kind"), d.get("tool"), d.get("digest")) for d in stored],
    }


def summarize_condition(runs, classes):
    summary = {}
    for c in classes:
        c_runs = [r for r in runs if r["kind"] == c]
        n = len(c_runs)
        calls = [r["tool_calls"] for r in c_runs]
        mean_c = round(sum(calls) / n, 2) if n else 0.0
        summary[c] = {
            "n": n,
            "resolved": "%d of %d" % (sum(1 for r in c_runs if r["resolved"]), n),
            "wrong_fixes": sum(r["wrong_fixes"] for r in c_runs),
            "vetoes": "%d of %d" % (sum(1 for r in c_runs if r["vetoed"]), n),
            "holds": "%d of %d" % (sum(1 for r in c_runs if r["held"]), n),
            "fast_path": "%d of %d" % (sum(1 for r in c_runs if r["path"] == "fast"), n),
            "tool_calls": calls,
            "mean": mean_c,
        }
    return summary


def compare_reps(runs_a, runs_b):
    b_by_t = {r["ticket"]: r for r in runs_b}
    diffs = []
    for ra in runs_a:
        rb = b_by_t.get(ra["ticket"])
        if not rb or ra["tool_calls"] != rb["tool_calls"] or ra["sequence"] != rb["sequence"]:
            diffs.append(ra["ticket"])
    return diffs


def main():
    parser = argparse.ArgumentParser(description="Stage 5 eval harness")
    parser.add_argument("--tickets", choices=["heldout", "demo"], default="heldout")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    default_out = "docs/evidence/eval_demo_selftest.json" if args.tickets == "demo" else "docs/evidence/stage5_eval.json"
    out_path = Path(args.out or default_out)

    lag, synced_counts = seed.wait_synced()
    print("index sync: %.2fs, active memories: %s" % (lag, synced_counts))

    thresholds = {
        "FAST_SIM": config.FAST_SIM, "FAST_EVIDENCE": config.FAST_EVIDENCE,
        "TRUST_SIM": config.TRUST_SIM, "TRUST_EVIDENCE": config.TRUST_EVIDENCE,
        "VETO_SIM": config.VETO_SIM, "VETO_EVIDENCE": config.VETO_EVIDENCE,
        "HOLD_CONFIDENCE": config.HOLD_CONFIDENCE,
    }
    print("thresholds:", thresholds)

    mem_counts = get_memory_counts()
    print("memories per namespace and lifecycle:", mem_counts)

    raw_tickets = seed.load("demo_tickets" if args.tickets == "demo" else "heldout_tickets")
    classes = list(dict.fromkeys(t["kind"] for t in raw_tickets))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%H%M%S")

    print("\n%-10s %-4s %-16s %-11s %-9s %-11s %-9s %-12s %-7s %-6s %s" % (
        "condition", "rep", "ticket", "kind", "path", "tool_calls", "resolved", "wrong_fixes", "vetoed", "held", "chain ok"))

    all_runs = []

    # 1. Empty condition
    clean_scratch()
    assert db.memories().count_documents({"namespace": EMPTY_TEAM}) == 0, "scratch namespace not empty"
    empty_tickets = [dict(t, team=EMPTY_TEAM, id=t["id"] + "@empty") for t in raw_tickets]

    empty_runs = {"a": [], "b": []}
    for rep in ("a", "b"):
        for t in empty_tickets:
            r = run_one(t, "empty", rep, stamp)
            empty_runs[rep].append(r)
            all_runs.append(r)
            print("%-10s %-4s %-16s %-11s %-9s %-11d %-9s %-12d %-7d %-6s %s" % (
                r["condition"], r["rep"], r["ticket"], r["kind"], r["path"] or "", r["tool_calls"],
                str(r["resolved"]), r["wrong_fixes"], r["vetoed"], str(r["held"]), str(r["chain_ok"])))
    clean_scratch()

    # 2. Trained condition
    trained_runs = {"a": [], "b": []}
    for rep in ("a", "b"):
        for t in raw_tickets:
            r = run_one(t, "trained", rep, stamp)
            trained_runs[rep].append(r)
            all_runs.append(r)
            print("%-10s %-4s %-16s %-11s %-9s %-11d %-9s %-12d %-7d %-6s %s" % (
                r["condition"], r["rep"], r["ticket"], r["kind"], r["path"] or "", r["tool_calls"],
                str(r["resolved"]), r["wrong_fixes"], r["vetoed"], str(r["held"]), str(r["chain_ok"])))

    # Summaries
    summaries = {}
    for cond, runs_dict in [("empty", empty_runs), ("trained", trained_runs)]:
        runs = runs_dict["a"]  # n = tickets, not runs; rep b is compared with rep a below
        print(f"\nCONDITION: {cond} (rep a; n = number of tickets)")
        print("%-11s %-4s %-10s %-12s %-8s %-8s %-11s %-32s %s" % (
            "class", "n", "resolved", "wrong_fixes", "vetoes", "holds", "fast_path", "tool_calls", "mean"))
        c_summary = summarize_condition(runs, classes)
        for c in classes:
            s = c_summary[c]
            print("%-11s %-4d %-10s %-12d %-8s %-8s %-11s %-32s %.2f" % (
                c, s["n"], s["resolved"], s["wrong_fixes"], s["vetoes"], s["holds"], s["fast_path"], str(s["tool_calls"]), s["mean"]))
        diffs = compare_reps(runs_dict["a"], runs_dict["b"])
        msg = "identical" if not diffs else "differing tickets: %s" % diffs
        print(f"rep a vs rep b: {msg}")
        summaries[cond] = {"per_class": c_summary, "rep_comparison": msg}

    print()
    means_delta = {}
    for c in classes:
        em = summaries["empty"]["per_class"][c]["mean"]
        tm = summaries["trained"]["per_class"][c]["mean"]
        means_delta[c] = {"empty": em, "trained": tm}
        print(f"{c}: mean tool calls: empty {em:.2f} -> trained {tm:.2f}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tickets": args.tickets,
        "thresholds": thresholds,
        "memory_counts": mem_counts,
        "run_ids": [r["run_id"] for r in all_runs],
        "runs": all_runs,
        "summaries": summaries,
        "mean_tool_calls": means_delta,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
