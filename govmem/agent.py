"""The agent loop: a fixed, written tool pipeline. No model chooses tools.

Long path (7 tool calls):  recall_memory, get_account, check_service_status, fetch_logs,
                           lookup_catalog, apply_fix, verify_fix
Trusted path (6):          the same without lookup_catalog, when the logs confirm the recalled cause
Fast path (3):             recall_memory, apply_fix, verify_fix

Every step goes through Run.step: if a receipt for that step exists it is read back and the
tool is NOT called again; otherwise the tool runs and its receipt is written before the next step.
"""
import os
import signal
import time

from . import db, memory, policy, receipts, seed, world
from .embed import ticket_text


class Run:
    def __init__(self, run_id, out=print):
        self.run_id = run_id
        self.out = out
        self.stored = receipts.load(run_id)
        ok, message = receipts.verify_chain(self.stored, run_id)
        if not ok:
            raise SystemExit("run %s: receipt chain is broken (%s). Refusing to continue." % (run_id, message))
        self.position = 0
        self.replayed = 0
        self.executed = 0
        self.kill_after = int(os.environ.get("GOVMEM_KILL_AFTER", "0"))   # test hook: SIGKILL self after receipt N
        self.step_delay = float(os.environ.get("GOVMEM_STEP_DELAY", "0"))  # demo hook: pause so a human can kill -9

    def step(self, kind, tool, inputs, fn):
        if self.position < len(self.stored):
            doc = self.stored[self.position]
            if (doc["kind"], doc["tool"], doc["inputs"]) != (kind, tool, inputs):
                raise SystemExit("run %s seq %d: stored receipt is %s/%s, the pipeline expects %s/%s"
                                 % (self.run_id, doc["seq"], doc["kind"], doc["tool"], kind, tool))
            self.position += 1
            self.replayed += 1
            self._show(doc, replay=True)
            return doc["result"]
        result = fn()
        doc = receipts.append(self.run_id, kind, tool, inputs, result)
        self.position += 1
        self.executed += 1
        self._show(doc, replay=False)
        if self.kill_after and doc["seq"] == self.kill_after:
            self.out("     -- SIGKILL now (GOVMEM_KILL_AFTER=%d) --" % self.kill_after)
            os.kill(os.getpid(), signal.SIGKILL)
        if self.step_delay:
            time.sleep(self.step_delay)
        return result

    def tool(self, name, inputs, fn):
        return self.step("tool", name, inputs, fn)

    def event(self, name, inputs, result):
        return self.step("event", name, inputs, lambda: result)

    def _show(self, doc, replay):
        tag = "replayed from receipt, not re-run" if replay else "receipt %s" % doc["hash"][:10]
        if doc["kind"] == "tool":
            self.out("  [%02d] %-21s %s  (%s)" % (doc["seq"], doc["tool"], _brief(doc), tag))
        else:
            self.out("  [%02d] ** %s ** %s  (%s)" % (doc["seq"], doc["tool"].upper(), _brief(doc), tag))


def _brief(doc):
    r, tool = doc["result"], doc["tool"]
    if tool == "recall_memory":
        if not r["hits"]:
            return "no active memory for this team"
        top = r["hits"][0]
        return "top-1 %s cosine %.4f evidence %.2f" % (top["memory"], top["similarity"], top["evidence"])
    if tool == "veto":
        i = doc["inputs"]
        return "%s blocked: cosine %.4f, evidence %.2f < 0.50 (fix %s not applied)" % (
            i["memory"], i["similarity"], i["evidence"], i["fix_id"])
    return ", ".join("%s=%s" % (k, v) for k, v in r.items())


def run_ticket(ticket, run_id=None, out=print):
    """Resolve one ticket. Safe to call again after a crash: it resumes from the receipts."""
    run_id = run_id or "run-" + ticket["id"]
    team, account, text = ticket["team"], ticket.get("account") or "", ticket_text(ticket)
    db.tickets().update_one({"_id": ticket["id"]}, {"$setOnInsert": dict(ticket, _id=ticket["id"], status="open")},
                            upsert=True)
    run = Run(run_id, out)
    if run.stored:
        out("  resuming %s: %d receipts found, chain verifies" % (run_id, len(run.stored)))

    recalled = run.tool("recall_memory", {"team": team, "ticket": ticket["id"]},
                        lambda: world.recall_memory(team, text))
    top = recalled["hits"][0] if recalled["hits"] else None
    decision = policy.decide(top["similarity"], top["evidence"]) if top else "none"
    if decision == "veto":
        run.event("veto", {"memory": top["memory"], "fix_id": top["fix_id"], "similarity": top["similarity"],
                           "evidence": top["evidence"]}, {"blocked": True, "reason": "evidence below veto line"})

    path, fix_id, resolved, wrong = "catalog", None, False, []
    if decision == "fast":
        path, fix_id = "fast", top["fix_id"]
        resolved = _apply_and_verify(run, account, fix_id)
        if not resolved:
            wrong.append(fix_id)
    if not resolved:
        info = run.tool("get_account", {"account": account}, lambda: world.get_account(account))
        if info["found"]:
            run.tool("check_service_status", {"region": info["region"]},
                     lambda: world.check_service_status(info["region"]))
            logs = run.tool("fetch_logs", {"account": account}, lambda: world.fetch_logs(account))
            if decision == "trusted" and logs["cause"] == top["cause"]:
                path, fix_id = "trusted", top["fix_id"]
            elif logs["cause"]:
                path = "catalog"
                fix_id = run.tool("lookup_catalog", {"cause": logs["cause"]},
                                  lambda: world.lookup_catalog(logs["cause"]))["fix_id"]
            if fix_id and fix_id not in wrong:
                resolved = _apply_and_verify(run, account, fix_id)
                if not resolved:
                    wrong.append(fix_id)

    used_memory = top if path in ("fast", "trusted") and resolved else None
    conf = policy.confidence(path, top["similarity"] if top else 0.0, top["evidence"] if top else 0.0, resolved)
    hold = policy.must_hold(conf)
    candidate = None
    if resolved and path == "catalog":
        fix = seed.catalog()[fix_id]
        known = db.memories().find_one({"namespace": team, "lifecycle": "active", "fix_id": fix_id}, {"_id": 1})
        if not known:  # do not queue a duplicate of a fix the team already holds
            candidate = memory.propose(team, text, fix, actor="agent", source_ticket=ticket["id"])["_id"]
            run.event("candidate", {"memory": candidate, "fix_id": fix_id},
                      {"lifecycle": "candidate", "review": "rev-" + candidate})
    if hold:
        review = "rev-" + candidate if candidate else memory.open_hold(ticket["id"], team, run_id, fix_id, conf)
        run.event("hold", {"confidence": conf, "line": 0.70, "review": review},
                  {"waiting_for": "human", "reason": "confidence below hold line"})
    status = "held" if hold else ("resolved" if resolved else "escalated")
    final = run.event("final", {"ticket": ticket["id"]}, {
        "status": status, "path": path, "fix_id": fix_id if resolved else None, "confidence": conf,
        "memory": used_memory["memory"] if used_memory else None, "wrong_fixes": wrong,
        "vetoed": top["memory"] if decision == "veto" else None, "candidate": candidate})
    db.tickets().update_one({"_id": ticket["id"]}, {"$set": {"status": status, "run_id": run_id}})
    return summary(run_id, executed=run.executed, replayed=run.replayed, final=final)


def _apply_and_verify(run, account, fix_id):
    run.tool("apply_fix", {"account": account, "fix_id": fix_id}, lambda: world.apply_fix(account, fix_id))
    return run.tool("verify_fix", {"account": account, "fix_id": fix_id},
                    lambda: world.verify_fix(account, fix_id))["resolved"]


def summary(run_id, executed=0, replayed=0, final=None):
    """Everything here is read back from the runs collection, not from process memory."""
    stored = receipts.load(run_id)
    ok, message = receipts.verify_chain(stored, run_id)
    final = final or next((d["result"] for d in stored if d["tool"] == "final"), None)
    return {"run_id": run_id, "tool_calls": sum(1 for d in stored if d["kind"] == "tool"),
            "receipts": len(stored), "executed_now": executed, "replayed": replayed,
            "chain_ok": ok, "chain": message, "final": final,
            "sequence": [d["digest"] for d in stored]}


def answer(result):
    """The text a support engineer reads. Fix text comes from the catalog or the approved memory."""
    final = result["final"]
    lines = ["  status: %s   path: %s   tool calls: %d   confidence: %.2f"
             % (final["status"].upper(), final["path"], result["tool_calls"], final["confidence"])]
    if final["vetoed"]:
        lines.append("  vetoed: %s (similar, but its evidence is below 0.50; it was not applied)" % final["vetoed"])
    if final["fix_id"]:
        mem = memory.resolve(final["memory"]) if final["memory"] else None
        fix = mem or seed.catalog()[final["fix_id"]]
        lines.append("  fix: %s" % (fix.get("fix_title") or fix.get("title")))
        for number, text in enumerate(fix.get("fix_steps") or fix.get("steps"), start=1):
            lines.append("    %d. %s" % (number, text))
        if mem:
            lines.append("  provenance: learned from ticket %s, proposed by %s, approved by %s (memory %s)"
                         % (mem["source_ticket"], mem["actor"], mem["approved_by"], mem["_id"]))
        else:
            lines.append("  provenance: fix catalog entry %s; not yet team memory" % final["fix_id"])
    if final["candidate"]:
        lines.append("  learned: CANDIDATE %s is waiting in the review queue. It is not recalled until a human promotes it."
                     % final["candidate"])
    if final["status"] == "held":
        lines.append("  HOLD: confidence %.2f is below 0.70. The ticket stays open until a human decides (govmem review list)."
                     % final["confidence"])
    if final["status"] == "escalated":
        lines.append("  ESCALATED: no verified fix. A human takes the ticket.")
    lines.append("  audit: %s (%s)" % (result["chain"], result["run_id"]))
    return "\n".join(lines)
