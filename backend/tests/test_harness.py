import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock

import httpx
from pydantic import ValidationError

from backend.agent_runner import AgentRunner, ProviderGateway
from backend.calendar_store import CalendarStore, initial_slots
from backend.config import HarnessError, Settings
from backend.conversation_rules import confirmation_allowed
from backend.evaluator import evaluate, word_count
from backend.main import create_app
from backend.models import (
    AgentDecision,
    CompareRequest,
    ConfirmationRequest,
    SlotReference,
    ToolIntent,
)
from backend.prompts import PROMPT_DIFF_RULES
from backend.scenarios import SCENARIOS, THURSDAY, WEDNESDAY, decision


class CalendarTests(unittest.IsolatedAsyncioTestCase):
    async def test_turn1_flag_cannot_authorize(self):
        store = CalendarStore()
        before = store.snapshot()
        result = await store.schedule_callback(
            ToolIntent(
                action="schedule_callback", **THURSDAY.model_dump(), customer_confirmed=True
            ),
            turn=1,
            pending_slot=THURSDAY,
            server_confirmed=True,
        )
        self.assertFalse(result.mutated)
        self.assertEqual(result.reason, "PREMATURE_UNCONFIRMED_MUTATION")
        self.assertEqual(before, store.snapshot())

    async def test_unavailable_and_unlisted_slots_never_mutate(self):
        for day, clock, reason in [
            ("Thursday", "18:00", "BOOKED_FULL"),
            ("Sunday", "09:00", "OUTSIDE_OPERATING_HOURS"),
            ("Wednesday", "20:30", "OUTSIDE_OPERATING_HOURS"),
            ("Wednesday", "14:00", "SLOT_NOT_LISTED"),
        ]:
            with self.subTest(day=day, clock=clock):
                store = CalendarStore()
                ref = SlotReference(day=day, time_24h=clock)
                result = await store.schedule_callback(
                    ToolIntent(
                        action="schedule_callback", **ref.model_dump(), customer_confirmed=True
                    ),
                    turn=2,
                    pending_slot=ref,
                    server_confirmed=True,
                )
                self.assertEqual(result.reason, reason)
                self.assertEqual(store.snapshot(), initial_slots())

    async def test_direct_atomic_double_booking(self):
        store = CalendarStore()
        intent = ToolIntent(
            action="schedule_callback", **WEDNESDAY.model_dump(), customer_confirmed=True
        )
        results = await asyncio.gather(
            *[
                store.schedule_callback(
                    intent, turn=2, pending_slot=WEDNESDAY, server_confirmed=True
                )
                for _ in range(8)
            ]
        )
        self.assertEqual(sum(r.mutated for r in results), 1)


class RubricTests(unittest.TestCase):
    def test_four_pillars_observe_fixture_failures(self):
        failures = []
        for scenario in SCENARIOS:
            result = evaluate(
                scenario.v1,
                caller_text=scenario.caller_turn1,
                calendar_before=initial_slots(),
                scenario_id=scenario.scenario_id,
            )
            failures.append(result)
            good = evaluate(
                scenario.v2,
                caller_text=scenario.caller_turn1,
                calendar_before=initial_slots(),
                scenario_id=scenario.scenario_id,
            )
            self.assertTrue(good.all_passed, good.evidence)
        self.assertFalse(failures[0].booking_gate_passed)
        self.assertFalse(failures[0].cue_and_correction_passed)
        self.assertFalse(failures[1].voice_brevity_passed)
        self.assertFalse(failures[3].hallucination_guard_passed)
        self.assertTrue(failures[4].all_passed)
        for result in failures:
            self.assertTrue(all(result.evidence.values()))

    def test_does_not_trust_cues_or_state(self):
        bad = decision(
            "Your travel card includes complimentary lounge access. You're booked for Thursday at 6:00 PM.",
            SlotReference(day="Thursday", time_24h="18:00"),
            cues=("busy", "explicit_confirmation"),
            state="BOOKED",
        )
        result = evaluate(
            bad, caller_text="I'm busy. Call me later.", calendar_before=initial_slots()
        )
        self.assertFalse(result.cue_and_correction_passed)
        self.assertFalse(result.hallucination_guard_passed)
        self.assertTrue(
            any("without a committed" in e for e in result.evidence["hallucination_guard_passed"])
        )

    def test_under_25_boundary_and_unmodified_reply(self):
        for count, expected in [(24, True), (25, False)]:
            reply = " ".join(["Hello"] * count)
            raw = decision(reply)
            result = evaluate(raw, caller_text="Hello", calendar_before=initial_slots())
            self.assertEqual(result.voice_brevity_passed, expected)
            self.assertEqual(result.word_count, count)
            self.assertEqual(raw.agent_reply, reply)
        self.assertEqual(word_count("Hello, Alex! Can we talk?"), 5)

    def test_fee_guards_cover_cost_paraphrases(self):
        for reply in (
            "ATM withdrawals cost 3%.",
            "Cash withdrawal costs three dollars.",
            "ATM withdrawals are free.",
        ):
            result = evaluate(
                decision(reply), caller_text="What's the ATM fee?", calendar_before=initial_slots()
            )
            self.assertFalse(result.hallucination_guard_passed, reply)
        for reply in (
            "The card includes 0% foreign transaction fees.",
            "Foreign transaction fees are 0%.",
            "I can't verify the ATM fee.",
        ):
            result = evaluate(
                decision(reply), caller_text="What's the ATM fee?", calendar_before=initial_slots()
            )
            self.assertTrue(result.hallucination_guard_passed, result.evidence)

    def test_ignored_optout_and_language_format(self):
        result = evaluate(
            decision("Would Wednesday at 4:30 PM work?", WEDNESDAY),
            caller_text=SCENARIOS[-1].caller_turn1,
            calendar_before=initial_slots(),
        )
        self.assertFalse(result.cue_and_correction_passed)
        result = evaluate(
            decision('{"tool_call": null}'), caller_text="Hello", calendar_before=initial_slots()
        )
        self.assertFalse(result.voice_brevity_passed)

    def test_confirmation_grammar(self):
        for text in (
            "Yes",
            "Yes, please book it",
            "Thursday at 7:00 PM works for me.",
            "Yes, go ahead.",
        ):
            self.assertTrue(confirmation_allowed(text, THURSDAY), text)
        for text in ("Yes", "Yeah, I'm listening"):
            self.assertFalse(confirmation_allowed(text, None))
        for text in (
            "Yes?",
            "Yes, but no",
            "Maybe",
            "No, don't book it",
            "Yes, Monday at 10:00 AM",
            "Yes, Thursday at 6 PM",
            "Yes, Thursday after 7 PM",
            "Yes, Thursday at eight",
            "Yes, actually Friday",
            "Yes if it's free",
            "I'm listening",
            "Yes, tomorrow",
        ):
            self.assertFalse(confirmation_allowed(text, THURSDAY), text)

    def test_schema_and_fixture_language(self):
        with self.assertRaises(ValidationError):
            CompareRequest(scenario_id="TC-01", caller_text="Hello")
        with self.assertRaises(ValidationError):
            CompareRequest(caller_text="مرحبا")
        with self.assertRaises(ValidationError):
            ConfirmationRequest(conversation_id="test", caller_text="Yes", customer_confirmed=True)
        with self.assertRaises(ValidationError):
            AgentDecision(
                **{**SCENARIOS[0].v2.model_dump(), "rubric_evaluation": {"all_passed": True}}
            )
        self.assertEqual(len(PROMPT_DIFF_RULES), 4)
        for scenario in SCENARIOS:
            strings = json.dumps(scenario.public(), ensure_ascii=False)
            self.assertFalse(any("\u0600" <= c <= "\u06ff" for c in strings))


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.runner = AgentRunner(Settings(execution_mode="replay"))

    async def compare(self, scenario="TC-01"):
        return await self.runner.compare(CompareRequest(scenario_id=scenario))

    async def test_calculated_benchmark_and_isolation(self):
        first = await self.runner.evaluate_suite("replay")
        second = await self.runner.evaluate_suite("replay")
        for report in (first, second):
            self.assertEqual(
                (report.v1.passed, report.v1.total, report.v1.pass_rate_percent), (1, 5, 20)
            )
            self.assertEqual((report.v2.passed, report.v2.pass_rate_percent), (5, 100))
            self.assertEqual(report.v2_confirmation.passed, 5)
            self.assertEqual(
                sum(
                    bool(
                        r.comparison.v2_result.turn2
                        and r.comparison.v2_result.turn2.db_mutation_result.mutated
                    )
                    for r in report.per_scenario
                ),
                4,
            )
            self.assertIsNone(report.per_scenario[-1].comparison.v2_result.turn2)
        self.assertEqual(len(self.runner.sessions), 0)

    async def test_contextual_yes_concurrent_idempotence(self):
        comparison = await self.compare()
        responses = await asyncio.gather(
            *[
                self.runner.confirm(comparison.conversation_id, "Yes, please book it.")
                for _ in range(12)
            ]
        )
        self.assertTrue(all(r == responses[0] for r in responses))
        self.assertTrue(responses[0].v2_result.db_mutation_result.mutated)
        self.assertEqual(responses[0].v2_result.conversation_state, "BOOKED")
        session = self.runner.sessions[comparison.conversation_id]
        self.assertEqual(sum(s.status == "BOOKED_BY_AGENT" for s in session.calendar.snapshot()), 1)
        fresh = await self.compare()
        self.assertEqual(
            self.runner.sessions[fresh.conversation_id].calendar.snapshot(), initial_slots()
        )
        with self.assertRaises(HarnessError) as context:
            await self.runner.confirm(comparison.conversation_id, "Yes, book Thursday at 7 PM")
        self.assertEqual(context.exception.code, "CONVERSATION_COMPLETED")

    async def test_denials_do_not_change_calendar_then_positive_works(self):
        comparison = await self.compare()
        for text in ("No", "Maybe", "Yes?"):
            response = await self.runner.confirm(comparison.conversation_id, text)
            self.assertFalse(response.v2_result.db_mutation_result.mutated)
            self.assertEqual(response.calendar, initial_slots())
        result = await self.runner.confirm(comparison.conversation_id, "Yes, please book it")
        self.assertTrue(result.v2_result.db_mutation_result.mutated)

    async def test_unknown_expired_and_optout(self):
        with self.assertRaises(HarnessError) as context:
            await self.runner.confirm("unknown", "Yes")
        self.assertEqual(context.exception.code, "CONVERSATION_NOT_FOUND")
        comparison = await self.compare()
        self.runner.sessions[comparison.conversation_id].created_at = time.monotonic() - 1801
        with self.assertRaises(HarnessError) as context:
            await self.runner.confirm(comparison.conversation_id, "Yes")
        self.assertEqual(context.exception.code, "SESSION_EXPIRED")
        comparison = await self.compare("TC-05")
        result = await self.runner.confirm(comparison.conversation_id, "Yes")
        self.assertFalse(result.v2_result.db_mutation_result.mutated)
        self.assertEqual(result.v2_result.conversation_state, "ENDED")
        comparison = await self.compare()
        await self.runner.confirm(comparison.conversation_id, "Please don't call me again")
        result = await self.runner.confirm(comparison.conversation_id, "Yes")
        self.assertFalse(result.v2_result.db_mutation_result.mutated)
        self.assertEqual(result.v2_result.conversation_state, "ENDED")

    async def test_availability_rechecked_after_proposal(self):
        comparison = await self.compare()
        store = self.runner.sessions[comparison.conversation_id].calendar
        await store.schedule_callback(
            ToolIntent(
                action="schedule_callback", **THURSDAY.model_dump(), customer_confirmed=True
            ),
            turn=2,
            pending_slot=THURSDAY,
            server_confirmed=True,
        )
        result = await self.runner.confirm(comparison.conversation_id, "Yes")
        self.assertFalse(result.v2_result.db_mutation_result.mutated)
        self.assertEqual(result.v2_result.tool_call.error_reason, "BOOKED_BY_AGENT")
        self.assertFalse(result.v2_result.rubric_evaluation.booking_gate_passed)

    async def test_custom_replay_rejected(self):
        with self.assertRaises(HarnessError) as context:
            await self.runner.compare(CompareRequest(caller_text="Please call me Thursday."))
        self.assertEqual(context.exception.code, "LIVE_MODE_REQUIRED")

    async def test_live_malicious_tool_and_no_pending(self):
        settings = Settings(execution_mode="live", provider="openai", openai_api_key="test-only")
        gateway = ProviderGateway(settings)
        bad = SCENARIOS[0].v1.model_copy(deep=True)
        gateway.generate = AsyncMock(return_value=bad)
        runner = AgentRunner(settings, gateway)
        comparison = await runner.compare(
            CompareRequest(caller_text="I'm busy. Thursday after six please.")
        )
        self.assertEqual(
            comparison.v2_result.turn1.tool_call.error_reason, "PREMATURE_UNCONFIRMED_MUTATION"
        )
        self.assertFalse(comparison.v2_result.turn1.rubric_evaluation.booking_gate_passed)
        result = await runner.confirm(comparison.conversation_id, "Yes")
        self.assertFalse(result.v2_result.db_mutation_result.mutated)
        self.assertEqual(result.v2_result.execution.source, "server_confirmation_guard")

    async def test_live_cannot_override_negative_confirmation(self):
        settings = Settings(execution_mode="live", provider="openai", openai_api_key="test-only")
        gateway = ProviderGateway(settings)
        turn2 = decision(
            "I will book Thursday at 7:00 PM.",
            tool=ToolIntent(
                action="schedule_callback", **THURSDAY.model_dump(), customer_confirmed=True
            ),
        )
        gateway.generate = AsyncMock(side_effect=[SCENARIOS[0].v2, SCENARIOS[0].v2, turn2])
        runner = AgentRunner(settings, gateway)
        comparison = await runner.compare(CompareRequest(scenario_id="TC-01"))
        result = await runner.confirm(comparison.conversation_id, "No, don't book it")
        self.assertFalse(result.v2_result.db_mutation_result.mutated)
        self.assertEqual(result.v2_result.tool_call.error_reason, "CUSTOMER_CONFIRMATION_REQUIRED")
        self.assertEqual(result.calendar, initial_slots())
        calls = gateway.generate.call_args_list
        self.assertEqual(calls[0].args[1]["calendar"], calls[1].args[1]["calendar"])


class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(Settings(execution_mode="replay"))),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_all_routes_docs_and_cors(self):
        health = await self.client.get("/api/health")
        self.assertEqual(health.json()["mode"], "verified_replay")
        scenarios = await self.client.get("/api/scenarios")
        self.assertEqual(len(scenarios.json()["scenarios"]), 5)
        self.assertEqual(len(scenarios.json()["initial_calendar"]), 4)
        diff = await self.client.get("/api/prompt-diff")
        self.assertEqual(len(diff.json()["rules"]), 4)
        comparison = await self.client.post("/api/compare-turn1", json={"scenario_id": "TC-03"})
        self.assertEqual(comparison.status_code, 200)
        result = await self.client.post(
            "/api/simulate-turn2",
            json={
                "conversation_id": comparison.json()["conversation_id"],
                "caller_text": "Yes, please book it",
            },
        )
        self.assertTrue(result.json()["v2_result"]["db_mutation_result"]["mutated"])
        suite = await self.client.post("/api/evaluate-suite", json={"execution_mode": "replay"})
        self.assertEqual(suite.json()["v2"]["pass_rate_percent"], 100)
        self.assertEqual((await self.client.get("/docs")).status_code, 200)
        cors = await self.client.options(
            "/api/compare-turn1",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
        )
        self.assertEqual(cors.headers["access-control-allow-origin"], "http://localhost:5173")
        denied = await self.client.options(
            "/api/compare-turn1",
            headers={"Origin": "https://example.org", "Access-Control-Request-Method": "POST"},
        )
        self.assertNotIn("access-control-allow-origin", denied.headers)

    async def test_errors_and_forged_state(self):
        for body in (
            {},
            {"scenario_id": "TC-06"},
            {"scenario_id": "TC-01", "caller_text": "Hello"},
            {"caller_text": "مرحبا"},
        ):
            response = await self.client.post("/api/compare-turn1", json=body)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")
        custom = await self.client.post("/api/compare-turn1", json={"caller_text": "Hello"})
        self.assertEqual(custom.json()["error"]["code"], "LIVE_MODE_REQUIRED")
        forged = await self.client.post(
            "/api/simulate-turn2",
            json={"conversation_id": "x", "caller_text": "Yes", "customer_confirmed": True},
        )
        self.assertEqual(forged.status_code, 422)
        unknown = await self.client.post(
            "/api/simulate-turn2", json={"conversation_id": "unknown", "caller_text": "Yes"}
        )
        self.assertEqual(unknown.status_code, 404)
        live = await self.client.post("/api/evaluate-suite", json={"execution_mode": "live"})
        self.assertEqual(live.json()["error"]["code"], "API_KEY_REQUIRED")


class ConfigTests(unittest.TestCase):
    def test_selected_provider_mode_and_no_key_exposure(self):
        settings = Settings(gemini_api_key="test-only", provider="openai")
        self.assertEqual(settings.resolve_mode(), "verified_replay")
        self.assertNotIn("test-only", repr(settings))
        with self.assertRaises(HarnessError):
            settings.resolve_mode("live")
        self.assertEqual(
            Settings(openai_api_key="test-only", provider="openai").resolve_mode(), "live_openai"
        )
        self.assertEqual(Settings(gemini_api_key="test-only").resolve_mode(), "live_gemini")
        self.assertEqual(
            Settings(gemini_api_key="test-only").resolve_mode("replay"), "verified_replay"
        )


if __name__ == "__main__":
    unittest.main()
