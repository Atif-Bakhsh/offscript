"""Regressions for authorization and observable evaluation audit findings."""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock

from backend.agent_runner import AgentRunner, ProviderGateway
from backend.calendar_store import CalendarStore, initial_slots
from backend.config import HarnessError, Settings
from backend.evaluator import evaluate
from backend.models import CompareRequest, MutationResult, ToolIntent
from backend.scenarios import SCENARIOS, THURSDAY, WEDNESDAY, decision


def booking_decision(reply="I will book Thursday at 7 PM."):
    return decision(
        reply,
        tool=ToolIntent(
            action="schedule_callback", **THURSDAY.model_dump(), customer_confirmed=True
        ),
    )


class AuthorizationRegressions(unittest.IsolatedAsyncioTestCase):
    def live_runner(self, second_turn):
        settings = Settings(provider="openai", execution_mode="live", openai_api_key="test-only")
        gateway = ProviderGateway(settings)
        gateway.generate = AsyncMock(side_effect=[SCENARIOS[0].v2, SCENARIOS[0].v2, second_turn])
        return AgentRunner(settings, gateway)

    async def test_unpunctuated_questions_do_not_book(self):
        runner = AgentRunner(Settings(execution_mode="replay"))
        for question in ("Is that confirmed", "Is Thursday at 7 PM okay", "Is that slot fine"):
            comparison = await runner.compare(CompareRequest(scenario_id="TC-01"))
            response = await runner.confirm(comparison.conversation_id, question)
            self.assertFalse(response.v2_result.db_mutation_result.mutated, question)
            self.assertEqual(response.calendar, initial_slots())

    async def test_pending_state_uses_affirmative_offer_not_rejected_mentions(self):
        for reply, expected_pending in (
            ("Thursday at 6 PM is full. Would Thursday at 7 PM work?", THURSDAY),
            ("Thursday at 7 PM is unavailable.", None),
        ):
            raw = decision(reply, THURSDAY)
            runner = self.live_runner(booking_decision())
            runner.gateway.generate = AsyncMock(return_value=raw)
            comparison = await runner.compare(CompareRequest(scenario_id="TC-01"))
            self.assertEqual(runner.sessions[comparison.conversation_id].pending, expected_pending)
            runner.gateway.generate = AsyncMock(return_value=booking_decision())
            result = await runner.confirm(comparison.conversation_id, "Yes, please book it")
            self.assertEqual(
                result.v2_result.db_mutation_result.mutated, expected_pending is not None
            )
            if expected_pending is None:
                self.assertEqual(result.calendar, initial_slots())

    async def test_optout_survives_failed_provider_request(self):
        runner = self.live_runner(HarnessError("PROVIDER_TIMEOUT", "Provider timed out.", 504))
        comparison = await runner.compare(CompareRequest(scenario_id="TC-01"))
        with self.assertRaises(HarnessError):
            await runner.confirm(comparison.conversation_id, "Please don't call me again")
        session = runner.sessions[comparison.conversation_id]
        self.assertTrue(session.opted_out)
        self.assertIsNone(session.pending)
        result = await runner.confirm(comparison.conversation_id, "Yes")
        self.assertEqual(result.v2_result.conversation_state, "ENDED")
        self.assertFalse(result.v2_result.db_mutation_result.mutated)
        self.assertEqual(result.calendar, initial_slots())

    async def test_caller_time_changes_require_fresh_comparison(self):
        runner = AgentRunner(Settings(execution_mode="replay"))
        for change in (
            "Actually Wednesday at 4:30 PM instead",
            "Yes, Thursday at 6 PM",
            "Yes, but Wednesday instead",
            "Thursday at eight",
            "Eight PM please",
        ):
            comparison = await runner.compare(CompareRequest(scenario_id="TC-01"))
            response = await runner.confirm(comparison.conversation_id, change)
            self.assertEqual(response.v2_result.execution.source, "server_confirmation_guard")
            self.assertIn("new comparison", response.v2_result.agent_reply)
            later = await runner.confirm(comparison.conversation_id, "Yes, please book it")
            self.assertFalse(later.v2_result.db_mutation_result.mutated)
            self.assertEqual(later.calendar, initial_slots())

    async def test_model_changed_proposal_cannot_reauthorize_original(self):
        runner = self.live_runner(decision("Would Wednesday at 4:30 PM work?", WEDNESDAY))
        comparison = await runner.compare(CompareRequest(scenario_id="TC-01"))
        response = await runner.confirm(comparison.conversation_id, "Maybe")
        self.assertEqual(response.v2_result.agent_reply, "Would Wednesday at 4:30 PM work?")
        self.assertEqual(response.v2_result.execution.source, "live_model")
        result = await runner.confirm(comparison.conversation_id, "Yes")
        self.assertFalse(result.v2_result.db_mutation_result.mutated)
        self.assertEqual(result.calendar, initial_slots())

    async def test_changed_model_proposal_retains_unsafe_attempt_evidence(self):
        raw = decision(
            "I booked Wednesday at 4:30 PM. Enjoy complimentary lounge access!",
            WEDNESDAY,
            tool=ToolIntent(
                action="schedule_callback", **WEDNESDAY.model_dump(), customer_confirmed=True
            ),
            state="BOOKED",
        )
        runner = self.live_runner(raw)
        comparison = await runner.compare(CompareRequest(scenario_id="TC-01"))
        response = await runner.confirm(comparison.conversation_id, "Yes")
        result = response.v2_result
        self.assertEqual(result.agent_reply, raw.agent_reply)
        self.assertEqual(result.tool_call.status, "REJECTED")
        self.assertFalse(result.rubric_evaluation.booking_gate_passed)
        self.assertFalse(result.rubric_evaluation.hallucination_guard_passed)
        self.assertFalse(result.rubric_evaluation.cue_and_correction_passed)
        self.assertEqual(response.calendar, initial_slots())
        later = await runner.confirm(comparison.conversation_id, "Yes, please book it")
        self.assertFalse(later.v2_result.db_mutation_result.mutated)

    async def test_expiry_during_generation_cannot_commit(self):
        runner = self.live_runner(booking_decision())
        comparison = await runner.compare(CompareRequest(scenario_id="TC-01"))
        session = runner.sessions[comparison.conversation_id]

        async def expire(*args, **kwargs):
            session.created_at -= 1801
            return booking_decision()

        runner.gateway.generate = AsyncMock(side_effect=expire)
        with self.assertRaises(HarnessError) as caught:
            await runner.confirm(comparison.conversation_id, "Yes")
        self.assertEqual(caught.exception.code, "SESSION_EXPIRED")
        self.assertEqual(session.calendar.snapshot(), initial_slots())

    async def test_expiry_while_waiting_for_calendar_lock_cannot_commit(self):
        store = CalendarStore()
        await store._lock.acquire()
        task = asyncio.create_task(
            store.schedule_callback(
                booking_decision().tool_call,
                turn=2,
                pending_slot=THURSDAY,
                server_confirmed=True,
                expires_at=time.monotonic() + 0.02,
            )
        )
        try:
            await asyncio.sleep(0.04)
        finally:
            store._lock.release()
        with self.assertRaises(HarnessError) as caught:
            await task
        self.assertEqual(caught.exception.code, "SESSION_EXPIRED")
        self.assertEqual(store.snapshot(), initial_slots())


class EvaluationRegressions(unittest.TestCase):
    def score(self, reply, proposed=THURSDAY, **kwargs):
        return evaluate(
            decision(reply, proposed),
            caller_text=SCENARIOS[0].caller_turn1,
            calendar_before=initial_slots(),
            scenario_id="TC-01",
            **kwargs,
        )

    def test_unavailable_explanation_then_exact_offer_passes(self):
        result = self.score("Thursday at 6 PM is full. Would Thursday at 7 PM work?")
        self.assertTrue(result.all_passed, result.evidence)

    def test_denied_or_mismatched_pairs_fail(self):
        for reply in (
            "Thursday at 7 PM is unavailable.",
            "Would Thursday at 6 PM or Monday at 7 PM work?",
        ):
            result = self.score(reply)
            self.assertFalse(result.hallucination_guard_passed, result.evidence)
            self.assertTrue(result.evidence["hallucination_guard_passed"])

    def test_negated_retracted_preference_and_booking_claim_pass(self):
        for reply in (
            "Not tomorrow. Would Thursday at 7 PM work?",
            "Nothing is booked yet. Would Thursday at 7 PM work?",
        ):
            result = self.score(reply)
            self.assertTrue(result.all_passed, result.evidence)

    def test_busy_context_survives_into_confirmation(self):
        raw = booking_decision(
            "I will book Thursday at 7 PM. Enjoy complimentary airport lounge access!"
        )
        result = evaluate(
            raw,
            caller_text="Yes",
            caller_history=(SCENARIOS[0].caller_turn1,),
            calendar_before=initial_slots(),
            turn=2,
            mutation=MutationResult(mutated=True, reason="BOOKED"),
            pending_slot=THURSDAY,
            server_confirmed=True,
        )
        self.assertFalse(result.cue_and_correction_passed)
        self.assertTrue(
            any("pitch" in evidence for evidence in result.evidence["cue_and_correction_passed"])
        )

    def test_blank_and_punctuation_only_speech_fail_unchanged(self):
        for reply in ("   ", "...", "!!!"):
            raw = decision(reply)
            result = evaluate(raw, caller_text="Hello", calendar_before=initial_slots())
            self.assertFalse(result.voice_brevity_passed)
            self.assertEqual(raw.agent_reply, reply)
