"""
Memoria — Guided Tutorial

An interactive REPL that wraps the Memoria REST API with narrative
framing and hints. Start here if you're new to the puzzle.

    pip install httpx
    python tutorial.py

For free-form iteration after the tutorial, use solver.py.
"""

import json
import sys

import httpx

from solver import (
    MemoriaClient,
    find_contradictions,
    show_attribute_detail,
    print_result,
    API_URL,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADER = """
╔══════════════════════════════════════╗
║            M E M O R I A             ║
╠══════════════════════════════════════╣
║  A memory contradiction puzzle box   ║
╚══════════════════════════════════════╝
"""

HELP_POLICY = """
  submit          Read policy.json and submit it
  policy          Show your current policy
  explore         High-level summary of the conclusion data
  look <attr>     Show all conclusions for one attribute
  questions       Show the questions your policy answers
  rules           Show the policy schema and scoring rules
  debug <attr>    Show issue details for a failing attribute
  status          Check your session (submissions, best score)
  hint            Get a context-aware hint
  help            Show this message
  quit            Exit
"""

HELP_CODE = """
  run             Execute your reconcile() from custom_solver.py
  submit          Submit policy.json (still works)
  explore         High-level summary of the conclusion data
  look <attr>     Show all conclusions for one attribute
  debug <attr>    Run reconcile() on one attribute and show result
  questions       Show the questions (all 30 now visible)
  solution        Show the answer key (unlocked at score >= 0.90)
  status          Check your session (submissions, best score)
  hint            Get a context-aware hint
  help            Show this message
  quit            Exit
"""

# Hints organized by score tier. Each tier has multiple hints that cycle
# when the solver asks repeatedly. Only the tier matching the current
# best_score is shown.
HINT_TIERS = [
    # (min_score, max_score, [list of hints to cycle through])
    (0.0, 0.0, [
        "You haven't submitted yet. Try: submit {}",
    ]),
    (0.0, 0.50, [
        "Your baseline is low. Type 'explore' to see the big picture.",
        "Try 'look preferred_language' — what do the timestamps tell you?",
        "Look at the timestamps. Do conclusions change over time? Some attributes have old values that outnumber new ones.",
        "Check the time_decay options: type 'rules' and look at the methods.",
    ]),
    (0.50, 0.65, [
        "You've unlocked the category breakdown. Which categories are failing?",
        "Some questions ask about a specific context (at_work, at_home). Without context awareness, the engine mixes all contexts together.",
        "Check context_strategy in 'rules' — what happens if you partition by context?",
        "Do you trust what Alex says about themselves as much as what you observe them doing? Try 'look exercise_frequency'.",
    ]),
    (0.65, 0.75, [
        "Look at your worst_attributes — the issue tags tell you what kind of problem each one has.",
        "source_conflict means self-reports disagree with observed behavior. Which source is more reliable?",
        "Some conclusions have a 'corrects' field. The corrections system can clean up stale data — and cascade to remove inferences built on it.",
        "Try tuning source_trust: lower self_reported, keep observed_behavior high.",
    ]),
    (0.75, 0.85, [
        "Some attributes don't change over time (like native_language). Do they need time decay? Check attribute_overrides.",
        "The remaining gains are in per-attribute fine-tuning. Different attributes need different strategies.",
        "Try adjusting confidence_penalty — it controls how much contradiction reduces confidence.",
        "Check your abstain_below threshold. Are you abstaining on answerable questions, or guessing on unanswerable ones?",
    ]),
    (0.85, 1.0, [
        "You're in the top tier. The remaining points come from very specific attribute overrides and calibration tuning.",
        "Look at which specific attributes are still wrong. Each one might need its own override.",
    ]),
]

CODE_HINT_TIERS = [
    (0.80, 0.85, [
        "Start by looking at your worst_attributes from the last run. Use 'debug <attr>' to investigate.",
        "Your reconcile() function receives all conclusions for an attribute. Check the 'corrects' and 'derived_from' fields.",
        "Try filtering by context when the question specifies one — 'at_work' energy is different from 'at_home' energy.",
        "Some attributes are stable (native_language never changes). Detect these and return high confidence.",
    ]),
    (0.85, 0.90, [
        "Calibration matters now. When you return 0.9 confidence, you should be right 90% of the time.",
        "For attributes with contradictions, lower your confidence proportionally to how contested they are.",
        "Try detecting drift: if recent conclusions consistently differ from old ones, trust the recent ones more.",
        "Unanswerable questions (very few conclusions, evenly split) should get abstention (return None).",
    ]),
    (0.90, 1.0, [
        "You've mastered it. Type 'solution' to see the full answer key.",
    ]),
]


# ---------------------------------------------------------------------------
# Tutorial REPL
# ---------------------------------------------------------------------------

class TutorialREPL:

    def __init__(self):
        self.client = MemoriaClient(API_URL)
        self.conclusions: list[dict] = []
        self.contradictions: dict = {}
        self.last_policy: dict = {}
        self.best_score: float = 0.0
        self.submission_count: int = 0
        self.hint_index: int = 0
        self.advanced_unlocked: bool = False
        self.phase: str = "policy"          # "policy" or "code"
        self.last_result: dict | None = None
        self.prev_result: dict | None = None
        self.commands_used: set = set()

    def run(self):
        """Onboard, then enter the REPL loop."""
        self._onboard()
        self._repl()

    # -------------------------------------------------------------------
    # Onboarding
    # -------------------------------------------------------------------

    def _onboard(self):
        print(HEADER)
        print("  A user named Alex has been observed for 12 months.")
        print("  The system collected structured conclusions about them —")
        print("  but the conclusions contradict each other.\n")
        print("  Your job: submit a reconciliation policy that tells")
        print("  the engine how to decide what to believe.\n")

        # Create session
        session_id = self.client.start_session()
        print(f"  Session: {session_id}")

        # Fetch and cache data
        self.conclusions = self.client.get_conclusions()
        self.contradictions = find_contradictions(self.conclusions)

        print(f"  Loaded {len(self.conclusions)} conclusions across {len(set(c['attribute'] for c in self.conclusions))} attributes.")
        print(f"  {len(self.contradictions)} attributes have contradicting values.\n")

        # Create policy.json if it doesn't exist
        import os
        if not os.path.exists("policy.json"):
            with open("policy.json", "w") as f:
                f.write("{}\n")
            print("  Created policy.json with an empty policy.")
        else:
            print("  Found existing policy.json.")

        print("  Edit it in your editor, then type 'submit' to test it.\n")
        print("  Type 'submit' now to see your baseline score.")
        print("  Type 'help' for available commands.\n")

    # -------------------------------------------------------------------
    # REPL loop
    # -------------------------------------------------------------------

    def _repl(self):
        commands = {
            "submit": self.cmd_submit,
            "run": self.cmd_run,
            "explore": self.cmd_explore,
            "look": self.cmd_look,
            "questions": self.cmd_questions,
            "rules": self.cmd_rules,
            "status": self.cmd_status,
            "hint": self.cmd_hint,
            "help": self.cmd_help,
            "policy": self.cmd_policy,
            "solution": self.cmd_solution,
            "debug": self.cmd_debug,
        }

        while True:
            try:
                line = input("memoria> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n  Goodbye.")
                break

            if not line:
                continue
            if line in ("quit", "exit", "q"):
                print("  Goodbye.")
                break

            # Split into command and args
            parts = line.split(None, 1)  # split on first whitespace
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            if cmd in commands:
                self.commands_used.add(cmd)
                try:
                    commands[cmd](args)
                except httpx.HTTPStatusError as e:
                    # Show the API's actual error message, not the raw HTTP error
                    try:
                        err = e.response.json()
                        print(f"  API error: {err.get('message', str(e))}")
                        if err.get("hint"):
                            print(f"  Hint: {err['hint']}")
                    except Exception:
                        print(f"  Error: {e}")
                except Exception as e:
                    print(f"  Error: {e}")
            else:
                print(f"  Unknown command: '{cmd}'. Type 'help' for options.")

    # -------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------

    def cmd_submit(self, args: str):
        # Always read from policy.json
        try:
            with open("policy.json") as f:
                self.last_policy = json.load(f)
        except FileNotFoundError:
            print("  policy.json not found. Creating one with an empty policy.")
            with open("policy.json", "w") as f:
                f.write("{}\n")
            self.last_policy = {}
        except json.JSONDecodeError as e:
            print(f"  Invalid JSON in policy.json: {e}")
            return

        result = self.client.submit(self.last_policy)
        self._handle_result(result)

    def cmd_run(self, args: str):
        """Execute custom_solver.py's reconcile() function against this session."""
        if self.phase != "code":
            print("  'run' is available after solving with a policy (score >= 0.80).")
            print("  Use 'submit' to test your policy.json first.")
            return

        # Dynamically import reconcile() — fresh each time so edits take effect
        import importlib.util
        try:
            spec = importlib.util.spec_from_file_location("custom_solver", "custom_solver.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            reconcile = mod.reconcile
        except FileNotFoundError:
            print("  custom_solver.py not found in this directory.")
            return
        except AttributeError:
            print("  custom_solver.py must define a reconcile() function.")
            return
        except Exception as e:
            print(f"  Error loading custom_solver.py: {e}")
            return

        # Fetch data using existing session
        conclusions = self.client.get_conclusions()
        questions = self.client.get_questions()

        # Group conclusions by attribute
        from collections import defaultdict
        by_attr = defaultdict(list)
        for c in conclusions:
            by_attr[c["attribute"]].append(c)

        # Run reconcile() for each question
        answers = []
        for q in questions:
            relevant = by_attr.get(q["attribute"], [])
            try:
                value, confidence = reconcile(q["attribute"], q.get("context"), relevant)
            except Exception as e:
                print(f"  Error in reconcile() for {q['attribute']}: {e}")
                return

            answers.append({
                "question_id": q["id"],
                "value": value,
                "confidence": round(max(0.0, min(1.0, confidence)), 4),
            })

        # Submit answers via the existing session
        result = self.client.submit_answers(answers)
        self._handle_result(result)

    def _handle_result(self, result: dict):
        """Shared result handling for both submit and run."""
        prev_advanced = self.advanced_unlocked

        # Store for diff
        self.prev_result = self.last_result
        self.last_result = result

        # Update local state
        self.submission_count = result["submission_number"]
        self.best_score = result["best_score"]
        self.advanced_unlocked = result.get("advanced_unlocked", False)

        # Print results
        print_result(result)

        # Show diff from previous submission
        if self.prev_result:
            self._print_diff(self.prev_result, result)

        # After first submission, nudge toward hints
        if self.submission_count == 1 and self.best_score < 0.50:
            print("\n  Type 'hint' if you're not sure what to try next.")

        # Announce advanced mode unlock
        if self.advanced_unlocked and not prev_advanced:
            print("\n  ── Advanced mode unlocked! ──")
            print("  10 hidden questions have been revealed.")
            print("  Type 'questions' to see all 30.")

        # Detect mastery (0.90)
        if result.get("mastered"):
            print("\n  ╔═════════════════════════════════════╗")
            print("  ║           PUZZLE MASTERED           ║")
            print("  ╚═════════════════════════════════════╝")
            if result.get("message"):
                print(f"\n  \"{result['message']}\"")
            print("\n  Type 'solution' to see the full answer key.")

        # Detect solve (0.80) — transition to code mode
        elif result.get("solved") and self.phase == "policy":
            self.phase = "code"
            self._ensure_custom_solver()
            print("\n  ╔═════════════════════════════════════╗")
            print("  ║            PUZZLE SOLVED            ║")
            print("  ╚═════════════════════════════════════╝")
            if result.get("message"):
                print(f"\n  \"{result['message']}\"")
            print("\n  ── Phase 2: Write your own reconciliation logic ──")
            print("  Edit custom_solver.py in your editor, then type 'run'.")
            print("  All your exploration commands still work (look, explore, etc).")
            print("  Reach 0.90 to master the puzzle and unlock the answer key.")

    def _print_diff(self, prev: dict, curr: dict):
        """Show score changes between submissions."""
        fields = [("Score", "total_score"), ("Accuracy", "accuracy"),
                  ("Calibration", "calibration"), ("Robustness", "robustness")]
        changes = []
        for label, key in fields:
            old_val = prev.get(key, 0)
            new_val = curr.get(key, 0)
            delta = new_val - old_val
            if abs(delta) >= 0.0001:
                sign = "+" if delta > 0 else ""
                changes.append(f"    {label:14s} {old_val:.4f} → {new_val:.4f} ({sign}{delta:.4f})")

        # Per-category deltas
        cat_changes = []
        if prev.get("per_category") and curr.get("per_category"):
            prev_cats = {c["category"]: c["accuracy"] for c in prev["per_category"]}
            curr_cats = {c["category"]: c["accuracy"] for c in curr["per_category"]}
            for cat in sorted(set(prev_cats) | set(curr_cats)):
                old_acc = prev_cats.get(cat, 0)
                new_acc = curr_cats.get(cat, 0)
                delta = new_acc - old_acc
                if abs(delta) >= 0.01:
                    sign = "+" if delta > 0 else ""
                    cat_changes.append(f"    {cat:22s} {old_acc:.0%} → {new_acc:.0%} ({sign}{delta:.0%})")

        if changes or cat_changes:
            print("\n  Changes from last submission:")
            for c in changes:
                print(c)
            if cat_changes:
                print("    Categories:")
                for c in cat_changes:
                    print(c)

    def _ensure_custom_solver(self):
        """Create custom_solver.py if it doesn't exist."""
        import os
        if not os.path.exists("custom_solver.py"):
            self._write_custom_solver_template()
            print("  Created custom_solver.py with a starter reconcile() function.")
        else:
            print("  Found existing custom_solver.py.")

    def _write_custom_solver_template(self):
        """Write a custom_solver.py template with a ~0.65 baseline."""
        template = '''"""
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
'''
        with open("custom_solver.py", "w") as f:
            f.write(template)

    def cmd_policy(self, args: str):
        """Show the current policy."""
        print(f"\n{json.dumps(self.last_policy, indent=2)}\n")

    def cmd_debug(self, args: str):
        """Show how the last submission resolved a specific attribute."""
        if not args:
            print("  Usage: debug <attribute>")
            if self.last_result and self.last_result.get("worst_attributes"):
                names = [wa["attribute"] for wa in self.last_result["worst_attributes"]]
                print(f"  Try: {', '.join(names)}")
            return

        attr = args.strip()

        # Show conclusions for context
        show_attribute_detail(self.conclusions, attr)

        # If in code mode, run reconcile on this attribute
        if self.phase == "code":
            import importlib.util
            try:
                spec = importlib.util.spec_from_file_location("custom_solver", "custom_solver.py")
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                reconcile = mod.reconcile
            except Exception as e:
                print(f"  Could not load reconcile(): {e}")
                return

            relevant = [c for c in self.conclusions if c["attribute"] == attr]
            # Find a question for this attribute to get context
            questions = self.client.get_questions()
            q_for_attr = [q for q in questions if q["attribute"] == attr]
            ctx = q_for_attr[0].get("context") if q_for_attr else None

            try:
                value, confidence = reconcile(attr, ctx, relevant)
                print(f"\n  Your reconcile() returns: value={value}, confidence={confidence:.4f}")
                if ctx:
                    print(f"  (for context: {ctx})")
            except Exception as e:
                print(f"  reconcile() error: {e}")

        # Show issue from last result if available
        if self.last_result and self.last_result.get("worst_attributes"):
            for wa in self.last_result["worst_attributes"]:
                if wa["attribute"] == attr:
                    print(f"  Last submission issue: {wa['issue']}")

    def cmd_explore(self, args: str):
        sources = {}
        contexts = {}
        attrs = {}

        for c in self.conclusions:
            sources[c["source"]] = sources.get(c["source"], 0) + 1
            contexts[c["context"]] = contexts.get(c["context"], 0) + 1
            attrs[c["attribute"]] = attrs.get(c["attribute"], 0) + 1

        print(f"\n  {len(self.conclusions)} conclusions across {len(attrs)} attributes")
        print(f"  {len(self.contradictions)} attributes have contradictions\n")

        print("  By source:")
        for src, count in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"    {src:20s}  {count}")

        print(f"\n  By context:")
        for ctx, count in sorted(contexts.items(), key=lambda x: -x[1]):
            print(f"    {ctx:20s}  {count}")

        print(f"\n  Contradicted attributes:")
        for attr, vals in sorted(self.contradictions.items()):
            print(f"    {attr:25s}  {' vs '.join(vals)}")
        print()

    def cmd_solution(self, args: str):
        """Show the full answer key (only available after solving)."""
        resp = self.client.client.get(f"/sessions/{self.client.session_id}/solution")
        if resp.status_code == 403:
            print("\n  The solution is locked. Keep improving your policy.\n")
            return
        resp.raise_for_status()
        sol = resp.json()

        print(f"\n  \"{sol['message']}\"\n")
        print(f"  {'Attribute':25s}  {'Your Answer':20s}  {'Correct':20s}  {'Conf':>5s}  Result")
        print(f"  {'-'*25}  {'-'*20}  {'-'*20}  {'-'*5}  {'-'*6}")
        for r in sol["results"]:
            yours = r["your_answer"] or "(abstained)"
            correct = r["correct_answer"] or "(unanswerable)"
            mark = "ok" if r["correct"] else "WRONG"
            ctx = f" [{r['context']}]" if r.get("context") else ""
            print(f"  {r['attribute'] + ctx:25s}  {yours:20s}  {correct:20s}  {r['confidence']:5.2f}  {mark}")

        s = sol["summary"]
        print(f"\n  {s['correct']}/{s['total']} correct, {s['wrong']} wrong, {s['abstained']} abstained\n")

    def cmd_look(self, args: str):
        if not args:
            # Show a few example attributes
            examples = list(self.contradictions.keys())[:5]
            print(f"  Usage: look <attribute>")
            print(f"  Try: {', '.join(examples)}")
            return

        attr = args.strip()
        relevant = [c for c in self.conclusions if c["attribute"] == attr]
        if not relevant:
            print(f"  No conclusions found for '{attr}'.")
            print(f"  Type 'explore' to see all attributes.")
            return

        show_attribute_detail(self.conclusions, attr)

    def cmd_questions(self, args: str):
        questions = self.client.get_questions()
        print(f"\n  {len(questions)} visible questions:\n")
        for q in questions:
            ctx = f"  context={q['context']}" if q.get("context") else ""
            print(f"    {q['attribute']}{ctx}")
        print(f"\n  Note: hidden questions are also scored but not shown here.\n")

    def cmd_rules(self, args: str):
        rules = self.client.get_rules()

        print("\n  === Policy Schema ===")
        print("  Each section is a JSON object. Example:")
        print('  {"time_decay": {"method": "exponential", "half_life_days": 60}}')

        methods = rules["time_decay"]["methods"]
        print(f"\n  time_decay: {{\"method\": \"{methods[0]}\" | \"{methods[1]}\" | ... }}")
        for param, desc in rules["time_decay"]["parameters"].items():
            print(f"    {param}: {desc}")

        sources = rules["source_trust"]["sources"]
        print(f"\n  source_trust: {{\"{sources[0]}\": 0.0-1.0, \"{sources[1]}\": 0.0-1.0, ...}}")

        methods = rules["context_strategy"]["methods"]
        print(f"\n  context_strategy: {{\"method\": \"{methods[0]}\" | \"{methods[1]}\"}}")

        methods = rules["contradiction_resolution"]["methods"]
        print(f"\n  contradiction_resolution: {{\"method\": \"{methods[0]}\" | \"{methods[1]}\" | ...}}")
        for param, desc in rules["contradiction_resolution"]["parameters"].items():
            print(f"    {param}: {desc}")

        print(f"\n  corrections: {{\"apply\": true/false, \"cascade\": true/false}}")

        print(f"\n  confidence:")
        for opt, desc in rules["confidence"]["base_from_options"].items():
            print(f"    base_from: \"{opt}\" — {desc}")
        for param, desc in rules["confidence"]["parameters"].items():
            print(f"    {param}: {desc}")

        print(f"\n  attribute_overrides: {{\"attr_name\": {{...partial policy...}}}}")

        print(f"\n  === Example policy.json ===\n")
        print('  {')
        print('    "time_decay": {"method": "exponential", "half_life_days": 60},')
        print('    "source_trust": {"self_reported": 0.5, "observed_behavior": 1.0},')
        print('    "context_strategy": {"method": "partition"},')
        print('    "corrections": {"apply": true, "cascade": true}')
        print('  }')

        print(f"\n  === Scoring ===\n")
        print(f"    accuracy:    {rules['scoring']['accuracy_weight']:.0%}  {rules['scoring']['accuracy_description']}")
        print(f"    calibration: {rules['scoring']['calibration_weight']:.0%}  {rules['scoring']['calibration_description']}")
        print(f"    robustness:  {rules['scoring']['robustness_weight']:.0%}  {rules['scoring']['robustness_description']}")
        print()

    def cmd_status(self, args: str):
        status = self.client.get_status()
        print(f"\n  Session:     {status['session_id']}")
        print(f"  Submissions: {status['submission_count']}")
        print(f"  Best score:  {status['best_score']:.4f}")
        print(f"  Advanced:    {'unlocked' if status['advanced_unlocked'] else 'locked'}\n")

    def cmd_hint(self, args: str):
        # Find the most relevant hint based on current state
        hint = self._get_hint()
        print(f"\n  {hint}\n")

    def cmd_help(self, args: str):
        print(HELP_CODE if self.phase == "code" else HELP_POLICY)

    # -------------------------------------------------------------------
    # Hint logic
    # -------------------------------------------------------------------

    def _get_hint(self) -> str:
        if self.submission_count == 0:
            return HINT_TIERS[0][2][0]

        # Use the right hint list for the current phase
        tiers = CODE_HINT_TIERS if self.phase == "code" else HINT_TIERS

        # Find the tier matching current best_score
        for min_score, max_score, hints in tiers:
            if min_score <= self.best_score < max_score:
                hint = hints[self.hint_index % len(hints)]
                self.hint_index += 1
                return hint

        # Fallback for scores at the very top
        return "Keep experimenting. Check 'rules' for options you haven't tried."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    repl = TutorialREPL()
    repl.run()


if __name__ == "__main__":
    main()
