"""
Memoria — Solver Starter Kit

Configure a reconciliation policy that tells the Memoria engine how to
resolve contradictions in a user's long-term memory. Submit your policy,
see how it scores, and iterate.

Quick start:
    pip install httpx
    python solver.py

The puzzle:
    A simulated user has been observed over 12 months. The system has ~270
    structured conclusions about them — preferences, behaviors, traits —
    but the conclusions contradict each other. People change, lie to
    themselves, behave differently in different contexts, and sometimes
    the inference system gets it wrong.

    Your job: configure a reconciliation POLICY (a JSON object) that tells
    the engine how to decide what to believe. The engine applies your policy
    to answer 30 questions about the user, and scores the results on:

    - Accuracy (40%):  Did you get the right answer?
    - Calibration (30%): When you said 0.8 confidence, were you right 80%?
    - Robustness (30%): Did you avoid confident wrong guesses? Did you
                        correctly abstain on unanswerable questions?

    No single strategy wins everywhere. The scoring rewards thoughtful
    tradeoffs, not brute force.

How to iterate:
    1. Run this file to see your baseline score
    2. Read the feedback — it tells you which CATEGORIES of questions
       you're failing on (not the answers themselves)
    3. Adjust the policy dict below
    4. Run again. Repeat until satisfied.

Full rules and policy schema: GET /rules on the API.
"""

import httpx
from collections import defaultdict

# ---------------------------------------------------------------------------
# Configuration — change this to point to your Memoria instance
# ---------------------------------------------------------------------------

import os
API_URL = os.environ.get("MEMORIA_URL", "https://memoria-puzzle.up.railway.app")


# ---------------------------------------------------------------------------
# Client — handles all API communication
# ---------------------------------------------------------------------------

class MemoriaClient:
    """Thin wrapper around the Memoria REST API."""

    def __init__(self, base_url: str = API_URL):
        self.client = httpx.Client(base_url=base_url, timeout=30.0)
        self.session_id: str | None = None

    def start_session(self) -> str:
        """Start a new solver session. Returns the session_id."""
        resp = self.client.post("/sessions")
        resp.raise_for_status()
        self.session_id = resp.json()["session_id"]
        return self.session_id

    def get_conclusions(self) -> list[dict]:
        """Fetch all conclusions about the user."""
        resp = self.client.get(f"/sessions/{self.session_id}/conclusions")
        resp.raise_for_status()
        return resp.json()["conclusions"]

    def get_questions(self) -> list[dict]:
        """Fetch the questions your policy will be scored against."""
        resp = self.client.get(f"/sessions/{self.session_id}/questions")
        resp.raise_for_status()
        return resp.json()["questions"]

    def get_rules(self) -> dict:
        """Fetch the full policy schema and scoring documentation."""
        resp = self.client.get("/rules")
        resp.raise_for_status()
        return resp.json()

    def get_attributes(self) -> dict:
        """Fetch all attribute definitions and valid values."""
        resp = self.client.get("/attributes")
        resp.raise_for_status()
        return resp.json()["attributes"]

    def submit(self, policy: dict) -> dict:
        """Submit a reconciliation policy. Returns scores + feedback."""
        resp = self.client.post(
            f"/sessions/{self.session_id}/submit",
            json=policy,
        )
        resp.raise_for_status()
        return resp.json()

    def submit_answers(self, answers: list[dict]) -> dict:
        """Submit answers directly. Each answer: {question_id, value, confidence}."""
        resp = self.client.post(
            f"/sessions/{self.session_id}/answers",
            json={"answers": answers},
        )
        resp.raise_for_status()
        return resp.json()

    def get_status(self) -> dict:
        """Check session status: submission count, best score, etc."""
        resp = self.client.get(f"/sessions/{self.session_id}")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Analysis helpers — use these to understand the data before tuning
# ---------------------------------------------------------------------------

def summarize_conclusions(conclusions: list[dict]) -> None:
    """Print a high-level summary of the conclusion data."""

    sources = defaultdict(int)
    contexts = defaultdict(int)
    attrs = defaultdict(int)

    for c in conclusions:
        sources[c["source"]] += 1
        contexts[c["context"]] += 1
        attrs[c["attribute"]] += 1

    print(f"Total conclusions: {len(conclusions)}")
    print(f"Unique attributes: {len(attrs)}")

    print(f"\nBy source:")
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {src}: {count}")

    print(f"\nBy context:")
    for ctx, count in sorted(contexts.items(), key=lambda x: -x[1]):
        print(f"  {ctx}: {count}")

    print(f"\nMost-observed attributes:")
    for attr, count in sorted(attrs.items(), key=lambda x: -x[1])[:10]:
        print(f"  {attr}: {count}")


def find_contradictions(conclusions: list[dict]) -> dict[str, list[str]]:
    """
    Find attributes that have conflicting values.
    Returns {attribute: [list of distinct values]}.
    """

    attr_values: dict[str, set[str]] = defaultdict(set)
    for c in conclusions:
        attr_values[c["attribute"]].add(c["value"])

    return {
        attr: sorted(vals)
        for attr, vals in attr_values.items()
        if len(vals) > 1
    }


def show_attribute_detail(conclusions: list[dict], attribute: str) -> None:
    """
    Show all conclusions for a specific attribute, sorted by timestamp.
    Useful for understanding the contradiction pattern for one attribute.
    """

    relevant = [c for c in conclusions if c["attribute"] == attribute]
    relevant.sort(key=lambda c: c["timestamp"])

    print(f"\n{attribute} ({len(relevant)} conclusions):")
    for c in relevant:
        date = c["timestamp"][:10]  # just the date part
        extra = ""
        if c.get("corrects"):
            extra = f"  [corrects {c['corrects']}]"
        if c.get("derived_from"):
            extra = f"  [derived from {c['derived_from']}]"
        print(f"  {date}  {c['value']:20s}  source={c['source']:20s}  context={c['context']}{extra}")


def print_result(result: dict) -> None:
    """Pretty-print submission results. Handles gated fields that may be null."""

    print(f"\n{'='*50}")
    print(f"  Total Score: {result['total_score']:.4f}")
    print(f"{'='*50}")
    print(f"  Accuracy:    {result['accuracy']:.4f}  (weight: 40%)")
    print(f"  Calibration: {result['calibration']:.4f}  (weight: 30%)")
    print(f"  Robustness:  {result['robustness']:.4f}  (weight: 30%)")
    print(f"  Submission:  #{result['submission_number']}")
    print(f"  Best score:  {result['best_score']:.4f}")

    if result.get("advanced_unlocked"):
        print(f"  >> Advanced mode unlocked!")

    # per_category is gated — unlocks at best_score >= 0.50
    if result.get("per_category"):
        print(f"\nPerformance by category:")
        for cat in result["per_category"]:
            bar = "█" * int(cat["accuracy"] * 10) + "░" * (10 - int(cat["accuracy"] * 10))
            print(f"  {cat['category']:20s}  {bar}  {cat['accuracy']:.0%}  ({cat['count']} questions)")
    else:
        print(f"\n  [Category breakdown unlocks at score >= 0.50]")

    # worst_attributes is gated — unlocks at best_score >= 0.65
    if result.get("worst_attributes"):
        print(f"\nWorst attributes:")
        for wa in result["worst_attributes"]:
            print(f"  {wa['attribute']:25s}  issue: {wa['issue']}")

    cs = result["contradiction_summary"]
    print(f"\nContradictions: {cs['detected']} contested, {cs['no_contradiction']} clear, {cs['abstained']} abstained")

    # calibration_hint is gated — unlocks at best_score >= 0.75
    if result.get("calibration_hint"):
        print(f"Hint: {result['calibration_hint']}")


# ============================================================
# YOUR POLICY — edit this and re-run
# ============================================================

policy = {
    # Start here. Every field is optional — missing fields use defaults.
    # Submit this as-is to see your baseline, then start experimenting.
    #
    # See GET /rules for the full schema, or the README for a quick reference.
}


# ============================================================
# Main — run this to submit your policy and see results
# ============================================================

def main():
    client = MemoriaClient()
    session_id = client.start_session()
    print(f"Session: {session_id}\n")

    # Step 1: Explore the data
    conclusions = client.get_conclusions()
    summarize_conclusions(conclusions)

    contradictions = find_contradictions(conclusions)
    print(f"\nContradicted attributes ({len(contradictions)}):")
    for attr, vals in sorted(contradictions.items()):
        print(f"  {attr}: {vals}")

    # Step 2: Look at the questions
    questions = client.get_questions()
    print(f"\nQuestions ({len(questions)}):")
    for q in questions[:8]:
        ctx = f"  context={q['context']}" if q.get("context") else ""
        print(f"  {q['attribute']}{ctx}")
    if len(questions) > 8:
        print(f"  ... and {len(questions) - 8} more")

    # Step 3: Submit your policy
    print("\n--- Submitting policy ---")
    result = client.submit(policy)
    print_result(result)

    # Step 4: Dig deeper into failing attributes (unlocks at score >= 0.65)
    if result.get("worst_attributes"):
        worst_attr = result["worst_attributes"][0]["attribute"]
        show_attribute_detail(conclusions, worst_attr)


if __name__ == "__main__":
    main()
