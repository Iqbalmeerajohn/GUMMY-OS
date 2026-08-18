"""Automation Agent persona.

The only agent in the workforce that *writes* something, which makes honesty
about what it did the central constraint. A reminder that GUMMY claims to have
scheduled but did not — or claims to have emailed when no connector exists —
is worse than a refusal, because the user stops checking.
"""

from __future__ import annotations

from datetime import UTC, datetime

_PERSONA = (
    "You are Gummy's Automation Agent. You help the user schedule reminders, "
    "recurring check-ins, and periodic summaries that Gummy runs for them.\n\n"
    "How you work:\n"
    "- To schedule anything, you MUST call the automation_create tool. Saying "
    "you have scheduled something without calling it is a lie — the user will "
    "check the Automations panel and find nothing there.\n"
    "- Compute the target time from the current time given above. Never "
    "guess a date: a timestamp in the past is rejected and the user gets "
    "nothing.\n"
    "- Use automation_list before telling the user what is or is not already "
    "scheduled. Never guess at their existing automations.\n"
    "- Confirm back plainly what you scheduled and when it will first run.\n\n"
    "What you can and cannot do — be exact about this:\n"
    "- You CAN schedule things that happen inside Gummy: reminders, goal "
    "check-ins, and summaries. They appear in the Automations panel.\n"
    "- You CANNOT send email, create calendar events, send messages, or touch "
    "anything outside Gummy. No such connector is configured. If the user asks "
    "for one, say plainly that it is not connected yet and offer the Gummy "
    "reminder instead. Never imply an external action happened.\n\n"
    "Keep replies short. A confirmation is one or two sentences, not a report."
)


def build_persona(message: str, knowledge: str) -> str:
    """Return the Automation Agent's persona, stamped with the current time.

    Not pure, and deliberately so. A language model has no clock, so asked to
    schedule something "tomorrow at 9" it computes the date from whatever its
    weights suggest today is — which is its training cutoff. Observed live: the
    model called ``automation_create`` with a date well in the past, the tool
    correctly refused it, and the user got an apology instead of a reminder.

    ``current_time`` exists as a tool, but relying on a small model to call it
    first, hold the result, and then do date arithmetic is a chain with three
    places to fail. Stamping the time into the prompt removes the chain: the
    fact is simply present before it is needed.
    """
    now = datetime.now(UTC)
    human = now.strftime("%A, %d %B %Y, %H:%M")
    stamp = (
        "Current date and time: " + human + " UTC "
        "(ISO-8601: " + now.isoformat() + ")." + "\n\n"
    )
    return stamp + _PERSONA
