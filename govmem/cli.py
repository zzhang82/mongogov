"""Command line entry: python -m govmem <command>."""
import argparse
import hashlib
import json
import re
import sys

from . import db, seed


def _run_ticket(ticket, run_id):
    from . import agent
    print("TICKET %s  team=%s  account=%s" % (ticket["id"], ticket["team"], ticket["account"]))
    print(ticket["subject"])
    res = agent.run_ticket(ticket, run_id=run_id)
    print(agent.answer(res))
    print("tool calls: %d (steps executed now: %d, steps replayed from receipts: %d)" % (
        res["tool_calls"], res["executed_now"], res["replayed"]))
    return 0


def _build_parser():
    parser = argparse.ArgumentParser(prog="govmem", description="Governed memory for a support agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="Stage 0: check the sandbox and the vector index")

    p_seed = sub.add_parser("seed", help="load today's seed data")
    p_seed.add_argument("--reset", action="store_true", help="empty the four collections first")

    sub.add_parser("probe", help="Stage 1: measure repeat-ticket similarity")

    p_ing = sub.add_parser("ingest", help="ingest a ticket")
    p_ing.add_argument("file", nargs="?", default=None, help="ticket file or - for stdin")
    p_ing.add_argument("--team", default=None, help="team namespace (default: team-support)")
    p_ing.add_argument("--account", default=None, help="account id")
    p_ing.add_argument("--id", default=None, help="ticket id")
    p_ing.add_argument("--run-id", default=None, help="run id")
    p_ing.add_argument("--seed-ticket", default=None, help="seed ticket id")

    p_res = sub.add_parser("resume", help="resume a run")
    p_res.add_argument("run_id", help="run id to resume")

    p_rev = sub.add_parser("review", help="manage review queue")
    s_rev = p_rev.add_subparsers(dest="review_cmd", required=True)
    p_list = s_rev.add_parser("list", help="list pending reviews")
    p_list.add_argument("--team", default=None, help="team namespace")
    p_prom = s_rev.add_parser("promote", help="promote a review")
    p_prom.add_argument("review_id", help="review id")
    p_prom.add_argument("--as", dest="who", required=True, help="approver name")
    p_rej = s_rev.add_parser("reject", help="reject a review")
    p_rej.add_argument("review_id", help="review id")
    p_rej.add_argument("--as", dest="who", required=True, help="approver name")
    p_rej.add_argument("--reason", required=True, help="rejection reason")

    p_rv = sub.add_parser("revise", help="propose a revised memory")
    p_rv.add_argument("memory_id", help="memory id to revise")
    p_rv.add_argument("--as", dest="who", required=True, help="author name")
    p_rv.add_argument("--step", action="append", dest="steps", required=True, help="fix step")
    p_rv.add_argument("--title", default=None, help="fix title/note")

    p_f = sub.add_parser("forget", help="retire an active memory")
    p_f.add_argument("memory_id", help="memory id to retire")
    p_f.add_argument("--as", dest="who", required=True, help="author name")
    p_f.add_argument("--reason", required=True, help="rejection reason")

    p_m = sub.add_parser("memories", help="list stored memories")
    p_m.add_argument("--team", default=None, help="team namespace")
    p_m.add_argument("--all", action="store_true", help="show all lifecycles")

    p_aud = sub.add_parser("audit", help="audit run receipts")
    p_aud.add_argument("run_id", help="run id to inspect")
    p_aud.add_argument("--compare", default=None, help="compare against another run id")

    return parser


def _handle_ingest(args):
    if args.seed_ticket:
        found = None
        for name in ("heldout_tickets", "demo_tickets", "probe_tickets"):
            for t in seed.load(name):
                if t.get("id") == args.seed_ticket:
                    found = t
                    break
            if found:
                break
        if not found:
            print("seed ticket %s not found" % args.seed_ticket, file=sys.stderr)
            return 1
        ticket = {
            "id": args.id or found["id"],
            "team": args.team or found.get("team", "team-support"),
            "account": args.account if args.account is not None else found.get("account", ""),
            "subject": found.get("subject", ""),
            "body": found.get("body", ""),
        }
    else:
        if not args.file or args.file == "-":
            raw = sys.stdin.read()
        else:
            with open(args.file) as f:
                raw = f.read()
        raw_id = "T-" + hashlib.sha256(raw.encode()).hexdigest()[:8]
        data = None
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                data = obj
        except Exception:
            pass
        if data is not None:
            ticket = {
                "id": args.id or data.get("id") or raw_id,
                "team": args.team or data.get("team") or "team-support",
                "account": args.account if args.account is not None else data.get("account", ""),
                "subject": data.get("subject", ""),
                "body": data.get("body", ""),
            }
        else:
            account = ""
            lines = []
            for line in raw.splitlines():
                m = re.match(r"^Account:\s*(\S+)", line, re.IGNORECASE)
                if m:
                    if not account:
                        account = m.group(1)
                else:
                    lines.append(line)
            subject = ""
            body_lines = []
            for line in lines:
                if not subject and line.strip():
                    subject = line.strip()
                elif subject:
                    body_lines.append(line)
            ticket = {
                "id": args.id or raw_id,
                "team": args.team or "team-support",
                "account": args.account if args.account is not None else account,
                "subject": subject,
                "body": "\n".join(body_lines).strip(),
            }
    return _run_ticket(ticket, args.run_id)


def _handle_resume(args):
    # The run's first receipt names its ticket. A killed run never reached the final status write,
    # so the receipts, not the ticket's status fields, are the source for resume.
    from . import receipts
    stored = receipts.load(args.run_id)
    doc = db.tickets().find_one({"_id": stored[0]["inputs"].get("ticket")}) if stored else None
    if not doc:
        print("ticket for run %s not found" % args.run_id, file=sys.stderr)
        return 1
    ticket = {
        "id": doc.get("id") or doc["_id"],
        "team": doc.get("team", "team-support"),
        "account": doc.get("account", ""),
        "subject": doc.get("subject", ""),
        "body": doc.get("body", ""),
    }
    return _run_ticket(ticket, args.run_id)


def _handle_review(args):
    from . import memory
    if args.review_cmd == "list":
        q = {"status": "pending"}
        if args.team:
            q["namespace"] = args.team
        items = list(db.reviews().find(q).sort("_id", 1))
        if not items:
            print("review queue is empty")
            return 0
        for r in items:
            print("%s  kind=%s  ticket=%s  proposed_by=%s" % (
                r["_id"], r["kind"], r["source_ticket"], r.get("proposed_by", "")))
            if r.get("memory_id"):
                mem = db.memories().find_one({"_id": r["memory_id"]}, {"embedding": 0})
                if mem:
                    print("  lifecycle: %s  evidence: %.2f" % (mem["lifecycle"], mem["evidence"]))
                    if mem.get("supersedes"):
                        print("  supersedes: %s" % mem["supersedes"])
                    print("  symptom: %s" % mem["symptom"])
                    print("  fix: %s" % mem["fix_title"])
                    for i, step in enumerate(mem.get("fix_steps", []), 1):
                        print("    %d. %s" % (i, step))
            elif r.get("kind") == "hold":
                print("  fix_id: %s  confidence: %.2f" % (r.get("fix_id"), r.get("confidence", 0.0)))
        return 0
    if args.review_cmd == "promote":
        mem = memory.promote(args.review_id, args.who)
        if mem is None:
            print("hold approved; ticket resolved")
        else:
            print("memory: %s  lifecycle: %s  evidence: %.2f  approved_by: %s" % (
                mem["_id"], mem["lifecycle"], mem["evidence"], mem["approved_by"]))
            from . import seed
            lag, _ = seed.wait_synced()  # recall must see the change before the next ticket
            print("vector index in sync after %.1fs" % lag)
        return 0
    if args.review_cmd == "reject":
        memory.reject(args.review_id, args.who, args.reason)
        print("rejected review %s" % args.review_id)
        return 0


def _handle_revise(args):
    from . import memory
    cand = memory.revise(args.memory_id, args.steps, args.who, note=args.title)
    print("candidate: %s  review: rev-%s" % (cand["_id"], cand["_id"]))
    print("the old version stays active until a human promotes the successor")
    return 0


def _handle_forget(args):
    from . import memory
    memory.forget(args.memory_id, args.who, args.reason)
    print("retired %s" % args.memory_id)
    return 0


def _handle_memories(args):
    q = {}
    if not args.all:
        q["lifecycle"] = "active"
    if args.team:
        q["namespace"] = args.team
    docs = list(db.memories().find(q, {"embedding": 0}).sort("_id", 1))
    fmt = "%-14s %-13s %-11s %-8s %-10s %-12s %-7s %-14s %s"
    print(fmt % ("id", "namespace", "lifecycle", "evidence", "actor", "approved_by", "fix_id", "supersedes", "superseded_by"))
    for d in docs:
        ev = "%.2f" % d["evidence"] if d.get("evidence") is not None else ""
        print(fmt % (
            d.get("_id", ""),
            d.get("namespace", ""),
            d.get("lifecycle", ""),
            ev,
            d.get("actor", "") or "",
            d.get("approved_by", "") or "-",
            d.get("fix_id", "") or "-",
            d.get("supersedes", "") or "-",
            d.get("superseded_by", "") or "-",
        ))
    return 0


def _handle_audit(args):
    from . import receipts
    stored = receipts.load(args.run_id)
    for r in stored:
        print("[%02d] %-5s %-20s %-10s %s %s" % (
            r["seq"], r["kind"], r["tool"], r["actor"], r["digest"], r["hash"][:10]))
    ok, message = receipts.verify(args.run_id)
    print("CHAIN %s: %s" % ("OK" if ok else "BROKEN", message))
    tools = sum(1 for r in stored if r["kind"] == "tool")
    print("tool receipts: %d" % tools)
    ret = 0 if ok else 1
    if args.compare:
        other = receipts.load(args.compare)
        s1 = [(r["kind"], r["tool"], r["digest"]) for r in stored]
        s2 = [(r["kind"], r["tool"], r["digest"]) for r in other]
        if s1 == s2:
            print("SAME SEQUENCE: %d steps" % len(s1))
        else:
            diff_idx = 1
            diff_step = (None, None)
            for i in range(max(len(s1), len(s2))):
                st1 = s1[i] if i < len(s1) else None
                st2 = s2[i] if i < len(s2) else None
                if st1 != st2:
                    diff_idx = i + 1
                    diff_step = (st1, st2)
                    break
            print("differing step %d: %s vs %s" % (diff_idx, diff_step[0], diff_step[1]))
            ret = 1
    return ret


def _dispatch(args):
    if args.cmd == "setup":
        from . import stage0
        stage0.main()
        return 0
    if args.cmd == "seed":
        count = seed.seed(reset=args.reset)
        counts = {s: db.memories().count_documents({"lifecycle": s}) for s in ("candidate", "active", "superseded", "retired")}
        print("seeded %d training tickets; memories by lifecycle: %s" % (count, counts))
        return 0
    if args.cmd == "probe":
        from . import probe
        return probe.main()
    if args.cmd == "ingest":
        return _handle_ingest(args)
    if args.cmd == "resume":
        return _handle_resume(args)
    if args.cmd == "review":
        return _handle_review(args)
    if args.cmd == "revise":
        return _handle_revise(args)
    if args.cmd == "forget":
        return _handle_forget(args)
    if args.cmd == "memories":
        return _handle_memories(args)
    if args.cmd == "audit":
        return _handle_audit(args)
    return 0


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        res = _dispatch(args)
        return res if res is not None else 0
    except Exception as exc:
        from . import memory
        if isinstance(exc, memory.GovernanceError):
            print("REFUSED: %s" % exc)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
