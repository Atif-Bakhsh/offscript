"""Conversation-local mock calendar with an atomic, server-authorized booking gate."""

import asyncio
import time

from .config import HarnessError
from .models import CalendarSlot, MutationResult, SlotReference, ToolIntent

SIMULATION_CONTEXT = {
    "reference_datetime": "2026-11-10T10:00:00+03:00",
    "reference_day": "Tuesday",
    "timezone": "Asia/Riyadh",
    "tomorrow": "Wednesday",
    "operating_hours": "Monday through Friday, 09:00 to 20:00, local time.",
    "calendar_scope": "Only listed slots are bookable. Each experiment starts with a fresh calendar.",
}


def initial_slots() -> list[CalendarSlot]:
    return [
        CalendarSlot(
            slot_id="wed-1630",
            day="Wednesday",
            time_24h="16:30",
            label="Wednesday at 4:30 PM",
            status="AVAILABLE",
        ),
        CalendarSlot(
            slot_id="thu-1800",
            day="Thursday",
            time_24h="18:00",
            label="Thursday at 6:00 PM",
            status="BOOKED_FULL",
        ),
        CalendarSlot(
            slot_id="thu-1900",
            day="Thursday",
            time_24h="19:00",
            label="Thursday at 7:00 PM",
            status="AVAILABLE",
        ),
        CalendarSlot(
            slot_id="mon-1000",
            day="Monday",
            time_24h="10:00",
            label="Monday at 10:00 AM",
            status="AVAILABLE",
        ),
    ]


def same_slot(a: SlotReference | None, b: SlotReference | None) -> bool:
    return a is not None and b is not None and (a.day, a.time_24h) == (b.day, b.time_24h)


class CalendarStore:
    def __init__(self) -> None:
        self._slots = initial_slots()
        self._lock = asyncio.Lock()

    def snapshot(self) -> list[CalendarSlot]:
        return [s.model_copy(deep=True) for s in self._slots]

    def find(self, ref: SlotReference) -> CalendarSlot | None:
        return next((s.model_copy() for s in self._slots if same_slot(s, ref)), None)

    def rejection_reason(self, ref: SlotReference) -> str | None:
        if ref.day in {"Saturday", "Sunday"} or not "09:00" <= ref.time_24h < "20:00":
            return "OUTSIDE_OPERATING_HOURS"
        slot = self.find(ref)
        if slot is None:
            return "SLOT_NOT_LISTED"
        if slot.status != "AVAILABLE":
            return slot.status
        return None

    async def schedule_callback(
        self,
        intent: ToolIntent,
        *,
        turn: int,
        pending_slot: SlotReference | None = None,
        server_confirmed: bool = False,
        expires_at: float | None = None,
    ) -> MutationResult:
        async with self._lock:
            if expires_at is not None and time.monotonic() >= expires_at:
                raise HarnessError(
                    "SESSION_EXPIRED", "This conversation has expired. Start a new comparison.", 410
                )
            reason: str | None
            if turn != 2:
                reason = "PREMATURE_UNCONFIRMED_MUTATION"
            elif not server_confirmed or not intent.customer_confirmed:
                reason = "CUSTOMER_CONFIRMATION_REQUIRED"
            elif not same_slot(intent, pending_slot):
                reason = "PENDING_SLOT_MISMATCH"
            else:
                reason = self.rejection_reason(intent)
            if reason:
                return MutationResult(mutated=False, reason=reason, slot=self.find(intent))
            slot = next(s for s in self._slots if same_slot(s, intent))
            slot.status = "BOOKED_BY_AGENT"
            return MutationResult(mutated=True, reason="BOOKED", slot=slot.model_copy())
