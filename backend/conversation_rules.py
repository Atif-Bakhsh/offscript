"""Conservative, shared English parsing; model claims never count as consent.

These deliberately small grammars are evidence checks, not general language
understanding. Unrecognized wording cannot authorize a calendar mutation.
"""

import re
from typing import cast

from .models import Day, SlotReference

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_DAY = re.compile(r"\b(?:" + "|".join(DAYS) + r")\b", re.I)
_CLOCK = re.compile(
    r"(?<![\w:])(?:(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?|"
    r"([01]?\d|2[0-3]):([0-5]\d))(?!\w)",
    re.I,
)
_REJECTION = re.compile(
    r"\b(?:unavailable|full|outside|closed|blocked|wrong|retracted|discard|ignore|"
    r"no|not|never|nothing|can't|cannot|don't|doesn't|won't|isn't|aren't|"
    r"wasn't|weren't|haven't|hasn't|hadn't)\b",
    re.I,
)
_CONNECTOR = re.compile(r"\b(?:and|or|but|however|instead)\b|,", re.I)


def normalized(text: str) -> str:
    return text.lower().replace("’", "'").replace("…", " ").strip()


def is_opt_out(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:do not call|don't call|stop calling|remove (?:me|my number)|not interested|no more calls|unsubscribe)\b",
            normalized(text),
        )
    )


def _clock_value(match: re.Match[str]) -> str:
    if match[3]:
        hour, minute = int(match[1]), int(match[2] or 0)
        if not 1 <= hour <= 12 or minute > 59:
            return "INVALID"
        return f"{hour % 12 + (12 if match[3].lower() == 'p' else 0):02d}:{minute:02d}"
    return f"{int(match[4]):02d}:{match[5]}"


def times_in_text(text: str) -> list[str]:
    """Read numeric times once; unknown time wording cannot grant consent."""
    return [_clock_value(match) for match in _CLOCK.finditer(text)]


def _clauses(text: str) -> list[str]:
    # Protect the punctuation inside a.m./p.m. before sentence splitting.
    value = re.sub(r"\b([ap])\.m\.", r"\1m", normalized(text))
    return re.split(r"[.!?;]|\b(?:but|however)\b", value)


def affirmative_slots(text: str) -> list[SlotReference]:
    """Extract actual offered day/time pairs, excluding local rejected mentions.

    A day carries forward within a clause ("Thursday at 6 PM or 7 PM"),
    never across sentences. Each time is bound to its nearest preceding day,
    or its following day in forms such as "7 PM on Thursday". Local polarity
    prevents a rejected slot from hiding or becoming a different open offer.
    """
    result: list[SlotReference] = []
    for clause in _clauses(text):
        clocks = list(_CLOCK.finditer(clause))
        days = list(_DAY.finditer(clause))
        previous_rejected = False
        for index, clock in enumerate(clocks):
            time = _clock_value(clock)
            if time == "INVALID":
                continue
            preceding = [day for day in days if day.end() <= clock.start()]
            following = [day for day in days if day.start() >= clock.end()]
            # In "7 PM on Thursday", the following day belongs to this clock,
            # even if another pair appeared earlier in the same sentence.
            following_owns_clock = following and re.fullmatch(
                r"\s*(?:on\s+)?", clause[clock.end() : following[0].start()]
            )
            day = (
                following[0]
                if following_owns_clock
                else (preceding[-1] if preceding else (following[0] if following else None))
            )
            if day is None:
                continue
            paired_days = [day]
            if day in preceding:
                # "Monday or Thursday at 7 PM" makes two offers, not one.
                for earlier in reversed(preceding[:-1]):
                    if re.fullmatch(
                        r"\s*(?:and|or|,)\s*",
                        clause[earlier.end() : paired_days[0].start()],
                    ):
                        paired_days.insert(0, earlier)
                    else:
                        break
            previous_end = clocks[index - 1].end() if index else 0
            next_start = clocks[index + 1].start() if index + 1 < len(clocks) else len(clause)
            start = previous_end
            # Keep qualifiers before a new day ("not Wednesday"), while a
            # connector separates the previous pair's availability explanation.
            prefix = clause[start : clock.start()]
            separators = list(_CONNECTOR.finditer(prefix))
            if separators:
                start += separators[-1].end()
            suffix = clause[clock.end() : next_start]
            separator = _CONNECTOR.search(suffix)
            end = clock.end() + separator.start() if separator else next_start
            region = clause[start:end]
            if _REJECTION.search(region):
                previous_rejected = True
                continue
            # A numeric mention without offer/scheduling wording is not enough.
            offers = re.search(
                r"\b(?:would|could|offer|available|open|free|work|works|book|"
                r"schedule|scheduled|callback|call you|how about|can do)\b",
                region,
            )
            bare = re.fullmatch(
                r"\s*(?:on\s+)?(?:"
                + "|".join(day.lower() for day in DAYS)
                + r")\s+(?:at\s+)?"
                + re.escape(clock.group())
                + r"\s*",
                region,
                re.I,
            )
            # "I can't do Thursday at 6 PM or Friday at 7 PM" rejects both.
            # Explicit positive wording can introduce a new available alternative.
            if bare and previous_rejected and not offers:
                continue
            if offers or bare:
                previous_rejected = False
                for paired_day in paired_days:
                    ref = SlotReference(day=cast(Day, paired_day.group().title()), time_24h=time)
                    if ref not in result:
                        result.append(ref)
    return result


def mentions_exact_slot(text: str, slot: SlotReference) -> bool:
    """Require one unambiguous affirmative offer matching the structured slot."""
    return affirmative_slots(text) == [slot]


def has_booking_claim(text: str) -> bool:
    """Detect affirmative completed-booking claims, respecting local negation."""
    for clause in _clauses(text):
        for claim in re.finditer(
            r"\b(?:booked|scheduled|confirmed your callback|reservation is confirmed)\b",
            clause,
        ):
            # Limit negation to this claim, not an unrelated prior sentence.
            prefix = clause[: claim.start()]
            separators = list(_CONNECTOR.finditer(prefix))
            if separators:
                prefix = prefix[separators[-1].end() :]
            if not _REJECTION.search(prefix):
                return True
    return False


def has_retracted_preference_claim(text: str) -> bool:
    """TC-01 evidence: tomorrow/Wednesday is retained rather than discarded."""
    for clause in _clauses(text):
        if re.search(r"\b(?:tomorrow|wednesday)\b", clause) and not _REJECTION.search(clause):
            return True
    return False


def requested_slot_change(text: str, pending: SlotReference | None) -> bool:
    """A changed or corrected time needs a fresh two-turn comparison."""
    if pending is None:
        return False
    value = normalized(text)
    days = {day.group().title() for day in _DAY.finditer(value)}
    times = set(times_in_text(value))
    if days and days != {pending.day}:
        return True
    if times and times != {pending.time_24h}:
        return True
    # Worded clock requests cannot be matched to the numeric pending slot.
    # Invalidate that authorization rather than letting a later "Yes" reuse it.
    clock_words = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    if re.search(
        r"\b(?:at\s+"
        + clock_words
        + r"|"
        + clock_words
        + r"\s*(?:[ap]\.?m\.?|o'clock)|noon|midnight)\b",
        value,
    ):
        return True
    return bool(
        re.search(
            r"\b(?:actually|instead|wait|i mean|reschedule|change|different|"
            r"tomorrow|today|next|later|after|before|around|morning|afternoon|evening)\b",
            value,
        )
    )


def confirmation_allowed(text: str, pending: SlotReference | None) -> bool:
    if pending is None or is_opt_out(text) or "?" in text:
        return False
    value = normalized(text)
    days = {day.group().title() for day in _DAY.finditer(value)}
    times = set(times_in_text(value))
    if (days and days != {pending.day}) or (times and times != {pending.time_24h}):
        return False
    # Substitute only an exact adjacent day/time expression. Unknown wording,
    # questions without punctuation, and reordered words fail the full grammar.
    slot_pattern = (
        r"\b(?:on\s+)?"
        + re.escape(pending.day.lower())
        + r"\s+(?:at\s+)?(?:"
        + _CLOCK.pattern
        + r")"
    )
    value = re.sub(slot_pattern, " slotref ", value, flags=re.I)
    value = re.sub(r"[,.!]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    positive = r"(?:yes|yeah|yep|sure|okay|ok|confirmed|perfect|fine)"
    target = r"(?:it|that|that slot|the slot|the callback|slotref)"
    action = (
        r"(?:(?:please )?(?:book|schedule) "
        + target
        + r"|(?:please )?go ahead(?: and (?:book|schedule) "
        + target
        + r")?"
        + r"|i (?:confirm(?: "
        + target
        + r")?|agree))"
    )
    agreement = (
        r"(?:"
        + target
        + r" (?:works(?: for me)?|is (?:fine|perfect|okay|ok))"
        + r"|(?:that )?sounds good(?: to me)?)"
    )
    body = r"(?:" + action + r"|" + agreement + r")"
    return bool(
        re.fullmatch(
            r"(?:"
            + positive
            + r"(?: (?:slotref|"
            + body
            + r"))?(?: "
            + body
            + r")?"
            + r"|"
            + body
            + r"(?: "
            + body
            + r")?)",
            value,
        )
    )
