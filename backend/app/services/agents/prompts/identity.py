"""Who Gummy is, and what it can honestly say it does.

The old persona was two sentences — "you are Gummy, the user's personal AI
assistant, be warm and concise". A model given that and asked "what can you do?"
has nothing to answer from, so it invents a plausible assistant. Observed live:

    "I can help you with various tasks. From answering questions, to helping
     with reminders, to even assisting with coding projects like GUMMY..."

Every clause there is guesswork, and "coding projects like GUMMY" is the model
reading the word GUMMY out of its own prompt.

Two things fix that. The model needs to know what this product actually is, and
it needs to know what it can actually do — where "actually" means *derived from
the registry*, not a prose list someone maintains by hand. A hardcoded
capability paragraph is a claim that starts rotting the day it is written;
:func:`capability_block` reads the agent manifests, the tool catalog, and the
live settings, so it cannot describe an agent that was removed or promise a
search backend that has no key.

The identity block is deliberately short, because it is prepended to *every*
prompt. The capability block is long, so it is added only when the user actually
asked what Gummy can do — otherwise every answer drifts toward reciting a
feature list.
"""

from __future__ import annotations

import re

from app.core.config import get_settings

# Always present. Kept tight — this rides on every turn, and a long identity
# block crowds out the user's actual context.
IDENTITY = (
    "You are Gummy, a personal AI operating system that runs on the user's own "
    "machine. You are not a generic chatbot: you keep long-term memory of what "
    "matters to this person, coordinate specialist agents, and use tools to do "
    "real work.\n\n"
    "How you speak:\n"
    "- Answer the question that was actually asked, first and directly.\n"
    "- Match length to the question. A greeting gets a line. A simple factual "
    "question gets a few sentences. Only a genuinely complex request gets "
    "structure.\n"
    "- Never open with 'How can I assist you today?', 'I'm here to help', or "
    "'I can help with a variety of tasks'. Say something specific instead.\n"
    "- Calm and natural, not eager. No exclamation-heavy enthusiasm, no emoji "
    "unless the user uses them first.\n"
    "- Never describe your own machinery — agents, tools, prompts, retrieval — "
    "unless the user asks about it."
)


def _tool_phrases() -> list[str]:
    """Human phrases for the tools that can actually run right now."""
    from app.services.agents.tools import catalog

    settings = get_settings()
    phrases: list[str] = []
    for spec in catalog.list_tools():
        if not spec.is_executable:
            continue  # modeled-only: declared, but nothing would happen
        if spec.key == "web_search" and not settings.web_search_enabled:
            continue  # no key configured — claiming it would be a lie
        phrases.append(
            {
                "calculator": "do exact calculations",
                "memory_read": "search what you already know about the user",
                "file_search": "search inside the user's uploaded documents",
                "file_list": "list the user's uploaded files",
                "current_time": "check the current date and time",
                "web_search": "search the live web",
                "doc_read": "read one of the user's uploaded documents",
                "automation_create": "create scheduled reminders and check-ins",
                "automation_list": "list the user's scheduled automations",
            }.get(spec.key, spec.name.lower())
        )
    return phrases


def capability_block() -> str:
    """What Gummy can honestly claim, derived from the running system.

    Read from the registry and the live settings rather than written out, so it
    cannot promise an agent that was removed or a backend that has no key. The
    limitations are stated in the same breath as the capabilities: a capability
    list that omits what is missing is the kind of answer that gets found out
    one question later.
    """
    from app.services.agents.registry import get_registry

    settings = get_settings()
    registry = get_registry()

    registered = registry.keys()  # a tuple, not a mapping
    agent_lines: list[str] = []
    for key, description in (
        (
            "career",
            "jobs, internships, scholarships, exams, resumes and " "career planning",
        ),
        ("learning", "explaining topics and building structured learning plans"),
        ("research", "investigating a question and organising what is found"),
        ("automation", "reminders, recurring check-ins and scheduled tasks"),
    ):
        if key in registered:
            agent_lines.append(f"- {description}")

    lines = [
        "When the user asks what you can do, answer from THIS list and nothing "
        "else. Do not invent capabilities, and do not pad the list.",
        "",
        "What you can genuinely do right now:",
        "- remember useful things from conversations and use them silently when "
        "they are relevant",
        *agent_lines,
        "- coordinate several of the above in one request when it needs them "
        "(for example: find opportunities, then build a learning plan for the "
        "biggest gap)",
    ]

    tools = _tool_phrases()
    if tools:
        lines.append("- use tools directly: " + ", ".join(tools))

    limitations = []
    if not settings.web_search_enabled:
        limitations.append(
            "live web search is not connected on this instance, so you cannot "
            "look anything up on the internet"
        )
    limitations.append("you cannot send email or create calendar events")
    limitations.append(
        "scheduled tasks only run while Gummy is running on this machine"
    )
    lines += [
        "",
        "Also true, and worth saying plainly:",
        *[f"- {item}" for item in limitations],
        "",
        # Shape, not tone. Left alone the model copies the lines above
        # verbatim, which reads like documentation; told instead to write
        # "flowing prose in your own words" it paraphrased a 3B-sized hole in
        # the middle — "I can help with various tasks and queries" — which is
        # the exact vagueness this whole block exists to prevent. So: keep the
        # list, cap its length, and demand the concrete words.
        # The brevity rules elsewhere in the prompt tell the model to keep
        # answers short and avoid bullets. Without this override it obeyed
        # them here too and truncated the list after three items, dropping
        # research, reminders and the limitation. This is the one question
        # where a list is the right answer, and it has to say so.
        "This particular answer IS allowed to be a list, and it should be "
        "complete. Ignore the general advice about keeping answers short and "
        "avoiding bullets — it does not apply to this question. Cover every "
        "area above; do not stop after two or three.",
        "",
        "Write the answer in this shape:",
        "1. One short opening line saying what you are.",
        "2. Four or five short bullets, a few words each, in your own "
        "phrasing — not the sentences above copied out.",
        "3. One line naming a real limitation from the list.",
        "4. One concrete example of a question they could ask you next.",
        "",
        "Stay specific. Name the actual areas — opportunities and careers, "
        "learning, research, reminders, your memory of them. Never fall back "
        "on vague phrases like 'various tasks', 'many things', or 'a wide "
        "range of topics': those say nothing, and the specifics are right "
        "there above you.",
    ]
    return "\n".join(lines)


# Deterministic, and only for the two shapes that genuinely need special
# handling. Everything else is left to the model — a lookup table of canned
# answers per question type would not survive the next agent we add.
_CAPABILITY_PATTERNS = (
    r"\bwhat can (you|u|gummy) do\b",
    r"\bwhat are (you|your) (capabilities|features)\b",
    r"\bwhat can i (use|ask) you for\b",
    r"\bhow can you help\b",
    r"\bwhat do you do\b",
    r"\bwhat is gummy\b",
    r"\bwho are you\b",
    r"\bwhat are you\b",
)
_CAPABILITY_RE = re.compile("|".join(_CAPABILITY_PATTERNS), re.IGNORECASE)

# A greeting and nothing else. The length bound is what stops "hi, can you
# research X for me" from being treated as small talk.
_GREETING_RE = re.compile(
    r"^\s*(hi|hey|hello|yo|hiya|good\s+(morning|afternoon|evening))"
    r"[\s!.,]*(gummy)?[\s!.,]*$",
    re.IGNORECASE,
)

# Written as a positive instruction with a concrete shape. The first version
# was a prohibition ("do not say 'how can I assist you today'") and the local
# 3B model simply paraphrased around it — "How may I assist you?". Telling a
# small model what to write works; telling it what not to write does not.
_GREETING_GUIDANCE = (
    "The user said hello and nothing else. Reply with ONE short sentence and "
    "then stop. Twelve words is already too long.\n"
    "Greet them back and ask what they are working on. Something as plain as "
    "'Hey — what are you working on?' is exactly right. Sound like a person, "
    "not a service desk.\n"
    "Do not add a second sentence. Do not offer help in the abstract, do not "
    "list anything, and do not use the words 'assist', 'help you with', or "
    "'today'."
)


def is_capability_question(message: str) -> bool:
    """True when the user is asking what Gummy is or what it can do."""
    return bool(_CAPABILITY_RE.search(message))


def is_greeting(message: str) -> bool:
    """True for a bare greeting with no request attached."""
    return bool(_GREETING_RE.match(message))


def guidance_for(message: str) -> str:
    """Extra system guidance for this specific message, or "".

    Empty for the overwhelming majority of turns: this exists to fix two shapes
    the model demonstrably gets wrong on its own, not to script conversations.
    """
    if is_greeting(message):
        return _GREETING_GUIDANCE
    if is_capability_question(message):
        return capability_block()
    return ""
