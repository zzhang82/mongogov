"""Controls that need no database: lifecycle guard (G1), memory shape, receipt chain (G6)."""
import copy

import pytest

from govmem import config, memory, receipts

FIX = {"fix_id": "F00", "cause": "c", "title": "t", "steps": ["one"]}
VEC = [0.0] * config.EMBED_DIMS


def make(**over):
    args = dict(memory_id="m1", namespace="team-a", symptom="s", fix=FIX, actor="dev", source_ticket="T1",
                embedding=VEC)
    args.update(over)
    return memory.build(**args)


@pytest.mark.parametrize("old,new,ok", [
    ("candidate", "active", True), ("candidate", "retired", True), ("active", "superseded", True),
    ("active", "retired", True), ("retired", "active", False), ("superseded", "active", False),
    ("candidate", "superseded", False), ("active", "candidate", False), ("retired", "retired", False),
])
def test_lifecycle_guard(old, new, ok):
    if ok:
        memory.check_transition(old, new)
    else:
        with pytest.raises(memory.GovernanceError):
            memory.check_transition(old, new)


def test_new_memory_is_candidate():
    assert make()["lifecycle"] == "candidate"


@pytest.mark.parametrize("field", ["namespace", "actor", "source_ticket", "symptom"])
def test_memory_needs_field(field):
    with pytest.raises(memory.GovernanceError):
        make(**{field: ""})


def test_active_needs_distinct_approver():
    with pytest.raises(memory.GovernanceError):
        make(lifecycle="active")
    with pytest.raises(memory.GovernanceError):
        make(lifecycle="active", approved_by="dev")
    assert make(lifecycle="active", approved_by="sarah")["approved_by"] == "sarah"


def test_recall_pipeline_always_filters_team_and_active():
    stage = memory.recall_pipeline("team-a", VEC)[0]["$vectorSearch"]
    assert stage["filter"] == {"namespace": "team-a", "lifecycle": "active"}
    with pytest.raises(memory.GovernanceError):
        memory.recall_pipeline("", VEC)


def chain(run_id, n):
    prev, out = receipts.genesis(run_id), []
    for seq in range(1, n + 1):
        body = {"run_id": run_id, "seq": seq, "kind": "tool", "tool": "t%d" % seq, "inputs": {"a": seq},
                "result": {"ok": True}, "actor": "agent", "ts": "2026-11-14T00:00:0%d" % seq}
        doc = dict(body, prev_hash=prev, hash=receipts.compute_hash(prev, body))
        out.append(doc)
        prev = doc["hash"]
    return out


def test_chain_verifies_and_tamper_fails():
    good = chain("r1", 5)
    assert receipts.verify_chain(good, "r1")[0]
    bad = copy.deepcopy(good)
    bad[2]["result"] = {"ok": False}
    ok, message = receipts.verify_chain(bad, "r1")
    assert not ok and "seq 3" in message
    assert not receipts.verify_chain(good[:2] + good[3:], "r1")[0]   # a removed receipt
    assert not receipts.verify_chain(good, "another-run")[0]          # wrong genesis


def test_receipts_tail_state():
    assert receipts.tail_state([]) == "empty"
    c = chain("r1", 3)
    assert receipts.tail_state(c) == "open"
    final_body = {"run_id": "r1", "seq": 4, "kind": "tool", "tool": "final", "inputs": {},
                  "result": {"status": "ok"}, "actor": "agent", "ts": "2026-11-14T00:00:04"}
    final_doc = dict(final_body, prev_hash=c[-1]["hash"], hash=receipts.compute_hash(c[-1]["hash"], final_body))
    c.append(final_doc)
    assert receipts.tail_state(c) == "complete"


def test_memory_validate_rejects_invalid_evidence():
    with pytest.raises(memory.GovernanceError, match="evidence must be between 0 and 1"):
        make(evidence=1.5)


def test_memory_validate_rejects_unknown_lifecycle():
    with pytest.raises(memory.GovernanceError, match="unknown lifecycle"):
        make(lifecycle="draft")

