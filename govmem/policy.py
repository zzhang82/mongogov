"""Decisions. Every one is a comparison with a number in config.py."""
from . import config

CATALOG_CONFIDENCE = 0.50  # a catalog fix that no human has approved as team memory


def decide(similarity, evidence):
    """What to do with the top recalled memory: 'veto', 'fast', 'trusted' or 'none'.

    The veto is checked first, so no later branch can apply a low-evidence memory.
    """
    if similarity >= config.VETO_SIM and evidence < config.VETO_EVIDENCE:
        return "veto"
    if similarity >= config.FAST_SIM and evidence >= config.FAST_EVIDENCE:
        return "fast"
    if similarity >= config.TRUST_SIM and evidence >= config.TRUST_EVIDENCE:
        return "trusted"
    return "none"


def confidence(path, similarity=0.0, evidence=0.0, verified=False):
    """The agent's confidence in the action it chose (G4)."""
    if not verified:
        return 0.0
    if path in ("fast", "trusted"):
        return round(min(similarity, evidence), 4)
    return CATALOG_CONFIDENCE


def must_hold(value):
    return value < config.HOLD_CONFIDENCE
