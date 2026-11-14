"""Stage 1 probe: raw cosine of repeat tickets against today's seeded memory."""
import datetime

from . import config, memory, policy, seed
from .embed import embed, ticket_text


def band(sim, evidence):
    return policy.decide(sim, evidence).upper()


def main():
    lag, counts = seed.wait_synced()
    print("%s index in sync after %.1fs; active memories per team: %s"
          % (datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), lag, counts))
    tickets = seed.load("probe_tickets")
    vectors = embed([ticket_text(t) for t in tickets])
    print("%-7s %-7s %-11s %-7s %-6s %-9s %-8s %-11s %s" % (
        "ticket", "kind", "top-1", "cosine", "atlas", "evidence", "band", "2nd", "2nd cos"))
    repeats, traps, wrong_top = [], [], []
    for ticket, vec in zip(tickets, vectors):
        hits = memory.recall(ticket["team"], vec)
        top, second = hits[0], hits[1]
        if top["_id"] != ticket["expect"]:
            wrong_top.append(ticket["id"])
        (repeats if ticket["kind"] == "repeat" else traps).append(top["similarity"])
        print("%-7s %-7s %-11s %-7.4f %-6.4f %-9.2f %-8s %-11s %.4f" % (
            ticket["id"], ticket["kind"], top["_id"], top["similarity"], top["search_score"], top["evidence"],
            band(top["similarity"], top["evidence"]), second["_id"], second["similarity"]))
    other = memory.recall("team-billing", vectors[0])
    print("isolation: %s under team-billing sees %s" % (tickets[0]["id"],
          [(h["_id"], h["namespace"], h["similarity"]) for h in other]))
    print("repeat top-1 cosine: min %.4f, max %.4f, n=%d (abort line %.2f, fast path %.2f)"
          % (min(repeats), max(repeats), len(repeats), config.PROBE_ABORT_SIM, config.FAST_SIM))
    print("trap top-1 cosine:   min %.4f, max %.4f, n=%d (veto floor %.2f)"
          % (min(traps), max(traps), len(traps), config.VETO_SIM))
    print("top-1 is not the expected memory for:", wrong_top or "none")
    ok = min(repeats) >= config.PROBE_ABORT_SIM and not wrong_top
    print("PROBE:", "PASS" if ok else "ABORT LINE HIT - stop and ask Frank")
    return 0 if ok else 1
