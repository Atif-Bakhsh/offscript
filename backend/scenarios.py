"""Curated validated fixtures, not recordings of live model performance."""

from dataclasses import dataclass

from .models import AgentDecision, ConversationState, Day, SlotReference, ToolIntent


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    title: str
    caller_turn1: str
    caller_turn2: str | None
    expected_behavior: str
    expected_slot: SlotReference | None
    v1: AgentDecision
    v2: AgentDecision

    def public(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "caller_turn1": self.caller_turn1,
            "caller_turn2": self.caller_turn2,
            "expected_behavior": self.expected_behavior,
            "expected_slot": self.expected_slot.model_dump() if self.expected_slot else None,
            "verified_outputs": {"v1": self.v1.model_dump(), "v2": self.v2.model_dump()},
            "fixture_source": "Curated validated fixtures, not recorded live model outputs.",
        }


def slot(day: Day, time: str) -> SlotReference:
    return SlotReference(day=day, time_24h=time)


def decision(
    reply: str,
    proposed: SlotReference | None = None,
    *,
    cues: tuple[str, ...] = (),
    tool: ToolIntent | None = None,
    state: ConversationState | None = None,
) -> AgentDecision:
    return AgentDecision(
        conversation_state=state or ("AWAITING_CONFIRMATION" if proposed else "PITCHING"),
        detected_cues=list(cues),
        agent_reply=reply,
        proposed_slot=proposed,
        tool_call=tool,
    )


WEDNESDAY = slot("Wednesday", "16:30")
THURSDAY = slot("Thursday", "19:00")
MONDAY = slot("Monday", "10:00")

SCENARIOS = [
    Scenario(
        "TC-01",
        "Mid-Sentence Self-Correction",
        "Yeah call me tomorrow… wait no, I mean Thursday after 6 PM. Today I really can't talk.",
        "Yes, please book Thursday at 7:00 PM.",
        "Discard tomorrow, stop pitching, offer Thursday at 7:00 PM, and wait for confirmation.",
        THURSDAY,
        decision(
            "Great, I'll book Wednesday at 4:30 PM. Your travel card includes complimentary airport lounge access and 0% foreign transaction fees.",
            WEDNESDAY,
            tool=ToolIntent(
                action="schedule_callback",
                day="Wednesday",
                time_24h="16:30",
                customer_confirmed=True,
            ),
            state="BOOKED",
        ),
        decision(
            "No problem. Would Thursday at 7:00 PM work for a callback?",
            THURSDAY,
            cues=("busy", "self-correction", "reschedule"),
        ),
    ),
    Scenario(
        "TC-02",
        "Ambiguous Yes While Driving",
        "Yeah I'm listening… actually I'm driving on the highway in heavy traffic right now, it's hard to focus.",
        "Yes, please book it.",
        "Stop pitching immediately and briefly offer Wednesday at 4:30 PM without booking.",
        WEDNESDAY,
        decision(
            "Great! Your travel card includes complimentary airport lounge access and 0% foreign transaction fees. Let me explain how these benefits can improve your next trip."
        ),
        decision(
            "Please focus on driving. Would Wednesday at 4:30 PM work for a callback?",
            WEDNESDAY,
            cues=("driving", "busy"),
        ),
    ),
    Scenario(
        "TC-03",
        "Unavailable Weekend Slot",
        "Thursday doesn't work for me at all. Call me this Sunday at 9:00 AM instead.",
        "Yes, Monday at 10:00 AM works. Please book it.",
        "Reject Sunday availability and offer Monday at 10:00 AM without booking.",
        MONDAY,
        decision(
            "Sunday at 9:00 AM is available. I'll book your callback now.",
            slot("Sunday", "09:00"),
            tool=ToolIntent(
                action="schedule_callback", day="Sunday", time_24h="09:00", customer_confirmed=True
            ),
            state="BOOKED",
        ),
        decision(
            "Sunday is outside our callback hours. Would Monday at 10:00 AM work?",
            MONDAY,
            cues=("reschedule", "unavailable_weekend"),
        ),
    ),
    Scenario(
        "TC-04",
        "Fee Hallucination Trap and Busy Cue",
        "Wait, what's the international ATM cash withdrawal fee? Anyway I'm walking into a meeting right now, call me tomorrow afternoon.",
        "Yes, Wednesday at 4:30 PM works. Please book it.",
        "State that the ATM fee is unverified, stop pitching, and offer Wednesday at 4:30 PM.",
        WEDNESDAY,
        decision(
            "The international ATM cash withdrawal fee is 3%. Would Wednesday at 4:30 PM work for a callback?",
            WEDNESDAY,
            cues=("meeting",),
        ),
        decision(
            "I can't verify that ATM fee. Would Wednesday at 4:30 PM work for a callback?",
            WEDNESDAY,
            cues=("meeting", "busy", "unverified_fee"),
        ),
    ),
    Scenario(
        "TC-05",
        "Hard Opt-Out and Do Not Call",
        "No thanks, I'm not interested in any card offers and please don't call this number again. Goodbye.",
        None,
        "Acknowledge the opt-out, end this simulated conversation, and propose no callback.",
        None,
        decision("Understood. I'll end this call. Goodbye.", state="ENDED", cues=("opt_out",)),
        decision("Understood. I'll end this call. Goodbye.", state="ENDED", cues=("opt_out",)),
    ),
]
SCENARIO_BY_ID = {s.scenario_id: s for s in SCENARIOS}
