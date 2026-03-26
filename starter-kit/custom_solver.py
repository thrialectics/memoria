"""
Memoria — Custom Solver

Edit the reconcile() function below. The tutorial's `run` command
will call it for each question using your current session.

Each conclusion looks like:
{
    "id": "con_042",
    "attribute": "preferred_language",
    "value": "python",
    "source": "self_reported",       # or observed_behavior, inferred, corrected
    "context": "general",            # or at_work, at_home, weekend, solo, social
    "timestamp": "2024-03-15T14:22:00",
    "corrects": null,                # or "con_023" if this corrects another
    "derived_from": [],              # or ["con_010"] if inferred from others
}
"""

from collections import defaultdict
from datetime import datetime
import math


def reconcile(attribute: str, context: str | None, conclusions: list[dict]) -> tuple[str | None, float]:
    """
    Given conclusions about an attribute, decide the current value.

    Args:
        attribute: The attribute being asked about
        context: The context (e.g., "at_work"), or None for general
        conclusions: All conclusions about this attribute

    Returns:
        (value, confidence) — value is your answer (or None to abstain),
        confidence is 0.0-1.0.

    This starter version handles time decay, source trust, and corrections.
    Improve it to handle context filtering, drift detection, and edge cases.
    """

    if not conclusions:
        return None, 0.0

    # === Apply corrections ===
    # Remove conclusions that have been corrected, and inferences built on them
    corrected_ids = {c["corrects"] for c in conclusions if c.get("corrects")}
    cascaded_ids = set()
    for c in conclusions:
        derived = c.get("derived_from") or []
        if isinstance(derived, list) and any(d in corrected_ids for d in derived):
            cascaded_ids.add(c["id"])
    removed = corrected_ids | cascaded_ids
    active = [c for c in conclusions if c["id"] not in removed]

    if not active:
        return None, 0.0

    # === Source trust weights ===
    source_weights = {
        "observed_behavior": 1.0,
        "self_reported": 0.6,
        "inferred": 0.3,
        "corrected": 1.0,
    }

    # === Time decay — exponential with 90-day half-life ===
    half_life = 90
    ref_time = datetime(2024, 12, 31)

    weighted_votes: dict[str, float] = defaultdict(float)
    for c in active:
        ts = datetime.fromisoformat(c["timestamp"])
        age_days = (ref_time - ts).total_seconds() / 86400
        time_w = 0.5 ** (age_days / half_life)
        source_w = source_weights.get(c["source"], 0.5)
        weighted_votes[c["value"]] += time_w * source_w

    if not weighted_votes:
        return None, 0.0

    winner = max(weighted_votes, key=weighted_votes.get)
    total = sum(weighted_votes.values())
    confidence = weighted_votes[winner] / total if total > 0 else 0.0

    return winner, confidence
