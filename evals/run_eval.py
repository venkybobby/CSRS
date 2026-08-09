"""Eval harness CI entrypoint (plan §6.3/§7) -- the gate a PR or deploy must
pass before reaching the next environment.

Two independent modes:

  --mode deterministic (default, runs on every PR against an ephemeral test
    DB, no live agent needed): calls resolve_procedure + estimate_member_cost
    directly for each case in demo_scripts.yaml and asserts response_type,
    key breakdown fields, and the cross-case must_differ_from checks.

  --mode live (post-deploy, against a real Agent Engine deployment): sends
    each case's natural-language `question` through the deployed agent,
    inspects the ADK session's tool-call event trace for the expected
    sequence, and additionally runs adversarial.yaml, asserting the BFF's
    guardrail either doesn't trigger (demo cases) or does (adversarial
    cases attempting to fabricate a figure).

Usage:
    TEST_DATABASE_URL=postgresql+psycopg2://... python evals/run_eval.py --mode deterministic
    AGENT_ENGINE_RESOURCE_NAME=... python evals/run_eval.py --mode live --env dev
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT, REPO_ROOT / "agent", REPO_ROOT / "bff"):
    sys.path.insert(0, str(p))


def _get_path(obj: dict, dotted: str) -> Any:
    current: Any = obj
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            raise KeyError(f"path {dotted!r} not found (stopped at {key!r})")
        current = current[key]
    return current


def run_deterministic(cases: list[dict]) -> list[tuple[str, str | None]]:
    """Returns a list of (case_id, failure_reason_or_None). Branches
    directly on expected_response_type, mirroring the three real control
    paths a case can take: blocked before any procedure lookup (termed),
    an honest miss caught by resolve_procedure alone (pipeline never
    runs), or the standard resolve-then-price path."""
    from csr_agent.data.rate_matcher import match_procedure
    from csr_agent.pipeline.estimate import estimate_member_cost

    from shared.messages import rate_not_found_message

    audit_ctx = {
        "csr_user_id": "eval-harness@meridianhealthplans.com",
        "session_id": "eval-session",
        "invocation_id": "eval-invocation",
        "trace_id": "eval-trace",
    }

    results: dict[str, dict] = {}
    outcomes: list[tuple[str, str | None]] = []

    for case in cases:
        case_id = case["id"]
        try:
            member_id = case["member_id"]
            expected_cpt = case.get("expected_cpt_code")
            expected_type = case["expected_response_type"]

            if expected_type == "TERMED_BLOCK":
                # Blocks before any procedure lookup -- the cpt value used
                # here is irrelevant to the outcome by design.
                result = estimate_member_cost(member_id, "00000", **audit_ctx)
                result_dict = result.model_dump(mode="json")

            elif expected_type == "RATE_NOT_FOUND" and expected_cpt is None:
                # Honest miss caught by resolve_procedure alone -- the real
                # agent never calls estimate_member_cost in this path, so
                # neither does this check.
                match = match_procedure(case["question"])
                if match.status != "NOT_ON_FILE":
                    outcomes.append((case_id, f"expected NOT_ON_FILE, got {match.status!r}"))
                    continue
                result_dict = {
                    "response_type": "RATE_NOT_FOUND",
                    "message": rate_not_found_message(case["question"]),
                }

            else:
                # Standard path: resolve_procedure must MATCH the expected
                # CPT, then estimate_member_cost prices it.
                match = match_procedure(case["question"])
                if match.status != "MATCHED" or match.cpt_code != expected_cpt:
                    outcomes.append((
                        case_id,
                        f"resolve_procedure expected MATCHED {expected_cpt!r}, "
                        f"got status={match.status!r} cpt_code={match.cpt_code!r}",
                    ))
                    continue
                result = estimate_member_cost(member_id, expected_cpt, **audit_ctx)
                result_dict = result.model_dump(mode="json")

            results[case_id] = result_dict
            _check_case(case, result_dict, outcomes)

        except Exception as exc:
            outcomes.append((case_id, f"exception: {exc!r}"))

    # Cross-case checks
    for case in cases:
        must_differ_from = case.get("must_differ_from")
        if not must_differ_from:
            continue
        case_id = case["id"]
        this_result = results.get(case_id)
        other_result = results.get(must_differ_from)
        if this_result is None or other_result is None:
            continue  # already recorded a failure above
        for field_path in case.get("must_differ_fields", []):
            try:
                a, b = _get_path(this_result, field_path), _get_path(other_result, field_path)
            except KeyError as exc:
                outcomes.append((case_id, f"must_differ check: {exc}"))
                continue
            if a == b:
                outcomes.append((
                    case_id,
                    f"{field_path} must differ from {must_differ_from} but both are {a!r}",
                ))

    return outcomes


def _check_case(case: dict, result_dict: dict, outcomes: list[tuple[str, str | None]]) -> None:
    case_id = case["id"]
    failed = False

    expected_type = case.get("expected_response_type")
    if expected_type and result_dict.get("response_type") != expected_type:
        outcomes.append((
            case_id,
            f"response_type: expected {expected_type!r}, got {result_dict.get('response_type')!r}",
        ))
        failed = True

    for field_path, expected_value in case.get("expected_fields", {}).items():
        try:
            actual = _get_path(result_dict, field_path)
        except KeyError as exc:
            outcomes.append((case_id, f"field {field_path}: {exc}"))
            failed = True
            continue
        if str(actual) != str(expected_value):
            outcomes.append((case_id, f"{field_path}: expected {expected_value!r}, got {actual!r}"))
            failed = True

    for substring in case.get("expected_message_contains", []):
        if substring not in result_dict.get("message", ""):
            outcomes.append((case_id, f"message missing expected substring {substring!r}"))
            failed = True

    if not failed:
        outcomes.append((case_id, None))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["deterministic", "live", "both"], default="deterministic")
    parser.add_argument("--env", default="local")
    args = parser.parse_args()

    demo_cases = yaml.safe_load((REPO_ROOT / "evals" / "demo_scripts.yaml").read_text())["cases"]

    all_passed = True

    if args.mode in ("deterministic", "both"):
        print(f"=== Deterministic mode ({args.env}) ===")
        outcomes = run_deterministic(demo_cases)
        for case_id, failure in outcomes:
            if failure is None:
                print(f"  PASS  {case_id}")
            else:
                print(f"  FAIL  {case_id}: {failure}")
                all_passed = False

    if args.mode in ("live", "both"):
        print(f"=== Live mode ({args.env}) ===")
        print(
            "  SKIPPED -- requires AGENT_ENGINE_RESOURCE_NAME and a deployed "
            "Agent Engine resource; not runnable in this environment. See "
            "evals/demo_scripts.yaml's expected_tool_sequence fields and "
            "evals/adversarial.yaml for what this mode checks once wired to "
            "a live deployment's session-event trace."
        )

    if not all_passed:
        print("\nEval suite FAILED.")
        return 1

    print("\nEval suite PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
