"""Run from the project root: python3 backend/cli_eval.py [--mode live]."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agent_runner import AgentRunner
from backend.config import ExecutionMode, HarnessError, load_settings, parse_execution_mode


async def run(mode: ExecutionMode) -> int:
    try:
        report = await AgentRunner(load_settings()).evaluate_suite(mode)
    except HarnessError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 2
    print(f"OffScript evaluation | {report.execution.mode}")
    print("Replay outputs are curated validated fixtures; live scores are observed results.")
    print(f"{'Scenario':<10} {'Test case':<38} {'v1':<8} {'v2':<8} {'v2 confirmation':<16}")
    print("-" * 86)
    for row in report.per_scenario:
        v1 = "PASS" if row.comparison.v1_result.turn1.rubric_evaluation.all_passed else "FAIL"
        v2 = "PASS" if row.comparison.v2_result.turn1.rubric_evaluation.all_passed else "FAIL"
        confirmed = "PASS" if row.confirmation_passed else "FAIL"
        print(f"{row.scenario_id:<10} {row.title:<38} {v1:<8} {v2:<8} {confirmed:<16}")
    print(
        f"Turn-1 all-pillar pass rate: v1 {report.v1.pass_rate_percent:g}% ({report.v1.passed}/{report.v1.total}) -> "
        f"v2 {report.v2.pass_rate_percent:g}% ({report.v2.passed}/{report.v2.total})"
    )
    print(
        f"v2 confirmation checks: {report.v2_confirmation.passed}/{report.v2_confirmation.total} "
        "(four bookings and one opt-out in replay)"
    )
    target = Path(__file__).with_name("eval_report.json")
    target.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Report saved: {target}")
    if mode == "replay" and (
        report.v1.passed != 1 or report.v2.passed != 5 or report.v2_confirmation.passed != 5
    ):
        print("Replay regression detected.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        type=parse_execution_mode,
        choices=("replay", "live", "auto"),
        default="replay",
        help="Defaults to replay even when a provider key is configured.",
    )
    return asyncio.run(run(parser.parse_args().mode))


if __name__ == "__main__":
    raise SystemExit(main())
