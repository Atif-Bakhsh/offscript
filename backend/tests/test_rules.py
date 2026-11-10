"""Regression coverage for the small, shared authorization grammar."""

import unittest

from backend.conversation_rules import (
    affirmative_slots,
    confirmation_allowed,
    has_booking_claim,
    has_retracted_preference_claim,
    mentions_exact_slot,
    requested_slot_change,
    times_in_text,
)
from backend.models import SlotReference
from backend.scenarios import SCENARIOS, THURSDAY


class ConversationRuleTests(unittest.TestCase):
    def test_explicit_affirmative_grammar(self):
        for value in (
            "Yes",
            "Yes, please book it.",
            "That works for me.",
            "Yes, please book Thursday at 7:00 PM.",
            "Yes, Thursday at 7 PM works. Please book it.",
            "Go ahead",
            "I confirm Thursday at 7 PM",
        ):
            with self.subTest(value=value):
                self.assertTrue(confirmation_allowed(value, THURSDAY))
        for scenario in SCENARIOS:
            if scenario.caller_turn2:
                self.assertTrue(confirmation_allowed(scenario.caller_turn2, scenario.expected_slot))

    def test_interrogatives_and_reordered_words_do_not_authorize(self):
        for value in (
            "Is that confirmed",
            "Is Thursday at 7 PM okay",
            "Is that slot fine",
            "Yes is that confirmed",
            "Can you book it",
            "Please is that confirmed",
            "Yes?",
            "Yes, but no",
            "Maybe",
            "Yes, Thursday at 6 PM",
            "Yes, tomorrow",
            "Thursday at 7 PM",
            "Yes, please Thursday at seven",
            "Yes if it's free",
        ):
            with self.subTest(value=value):
                self.assertFalse(confirmation_allowed(value, THURSDAY))
        self.assertFalse(confirmation_allowed("Yes", None))

    def test_proposal_pairs_and_local_rejections(self):
        self.assertTrue(
            mentions_exact_slot(
                "Thursday at 6:00 PM is full. Would Thursday at 7:00 PM work?", THURSDAY
            )
        )
        self.assertTrue(mentions_exact_slot("Not tomorrow. Would Thursday at 7 PM work?", THURSDAY))
        for value in (
            "Thursday at 7 PM is unavailable.",
            "Thursday at 7 PM isn't available.",
            "Would Thursday at 6 PM or Monday at 7 PM work?",
            "Would Monday or Thursday at 7 PM work?",
            "Thursday at 7 PM was mentioned earlier.",
        ):
            self.assertFalse(mentions_exact_slot(value, THURSDAY), value)
        self.assertEqual(
            affirmative_slots("Would Thursday at 6 PM or Monday at 7 PM work?"),
            [
                SlotReference(day="Thursday", time_24h="18:00"),
                SlotReference(day="Monday", time_24h="19:00"),
            ],
        )
        self.assertEqual(
            affirmative_slots("Would 6 PM on Thursday or 7 PM on Monday work?"),
            [
                SlotReference(day="Thursday", time_24h="18:00"),
                SlotReference(day="Monday", time_24h="19:00"),
            ],
        )

    def test_clock_mentions_are_not_duplicated_as_24_hour_times(self):
        self.assertEqual(times_in_text("Wednesday at 4:30 PM"), ["16:30"])
        self.assertEqual(times_in_text("Thursday at 19:00"), ["19:00"])
        self.assertEqual(times_in_text("Monday at 10:00 AM"), ["10:00"])
        self.assertEqual(times_in_text("13 PM"), ["INVALID"])

    def test_negated_alternatives_preserve_local_polarity(self):
        for text in (
            "Would Thursday at 7 PM work, not Wednesday at 4:30 PM?",
            "I can offer Thursday at 7 PM, not Monday at 10 AM.",
        ):
            self.assertEqual(affirmative_slots(text), [THURSDAY], text)
        self.assertEqual(affirmative_slots("I can't do Thursday at 6 PM or Friday at 7 PM."), [])
        self.assertEqual(
            affirmative_slots("Thursday at 6 PM is full, and Thursday at 7 PM is available."),
            [THURSDAY],
        )

    def test_negated_claims_remain_negated(self):
        for value in (
            "Nothing is booked yet.",
            "I have not booked it.",
            "Your callback isn't scheduled.",
        ):
            self.assertFalse(has_booking_claim(value), value)
        self.assertTrue(has_booking_claim("Your callback is booked."))
        self.assertTrue(
            has_booking_claim("Nothing was booked before. Your callback is booked now.")
        )
        self.assertFalse(
            has_retracted_preference_claim("Not tomorrow. Would Thursday at 7 PM work?")
        )
        self.assertTrue(
            has_retracted_preference_claim("Tomorrow works. Would Thursday at 7 PM work?")
        )

    def test_slot_changes_invalidate_old_authorization(self):
        for value in (
            "Actually Wednesday at 4:30 PM instead",
            "Yes, Thursday at 6 PM",
            "Tomorrow please",
            "Can we change the time",
            "Yes, but Wednesday instead",
            "Thursday after 7 PM",
            "Thursday at eight",
            "Eight PM please",
            "Could you call at eight o'clock",
        ):
            self.assertTrue(requested_slot_change(value, THURSDAY), value)
        for value in (
            "Maybe",
            "No",
            "Is that confirmed",
            "Yes, Thursday at 7 PM",
            "Please repeat the time",
            "I have eight questions",
        ):
            self.assertFalse(requested_slot_change(value, THURSDAY), value)


if __name__ == "__main__":
    unittest.main()
