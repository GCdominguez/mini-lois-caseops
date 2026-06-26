from __future__ import annotations

import re

CONCRETE_TERMS = (
    "record",
    "records",
    "report",
    "ledger",
    "witness",
    "policy",
    "policies",
    "coverage",
    "communication",
    "communications",
    "email",
    "emails",
    "document",
    "documents",
    "protocol",
    "protocols",
    "template",
    "claim",
    "claims",
)

ACTION_TERMS = (
    "request",
    "requesting",
    "requested but",
    "obtain",
    "obtaining",
    "contact",
    "contacting",
    "review",
    "reviewing",
    "collect",
    "collecting",
    "follow up",
    "following up",
)

PENDING_TERMS = (
    "missing",
    "not received",
    "not yet received",
    "hasn't been received",
    "has not been received",
    "not available",
    "not obtained",
    "not been obtained",
    "incomplete",
    "need to",
    "needs to",
    "still need",
)

VAGUE_PHRASES = (
    "pieces of the puzzle",
    "fill in",
    "move forward",
    "build a strong case",
    "better understanding",
    "more information",
    "keep an eye out",
    "point of contention",
    "potential defense",
    "potentially complicate",
    "case could",
    "client's case",
)

NEXT_STEP_MARKERS = (
    "next steps discussed were",
    "next steps discussed include",
    "next steps to take, including",
    "next steps include",
    "next steps were",
    "next steps are",
    "we still need to",
    "we also need to",
    "we need to",
    "need to get",
)


def clean_candidate(candidate: str) -> str:
    candidate = re.sub(r"^\*\*(.*?)\**$", r"\1", candidate).strip()
    candidate = re.split(r"\s+to\s+", candidate, maxsplit=1)[0]
    candidate = re.sub(r"^(get our hands on|get|the)\s+", "", candidate, flags=re.IGNORECASE)
    return candidate.strip(" -•\t").rstrip(".")


def contains_concrete_task_object(candidate: str) -> bool:
    lower = candidate.lower()
    return any(term in lower for term in CONCRETE_TERMS)


def has_action_signal(candidate: str) -> bool:
    lower = candidate.lower()
    return lower.startswith(ACTION_TERMS) or any(term in lower for term in PENDING_TERMS)


def is_vague_candidate(candidate: str) -> bool:
    lower = candidate.lower()
    return any(phrase in lower for phrase in VAGUE_PHRASES)


def add_candidate(candidates: list[str], candidate: str, *, allow_concrete_without_signal: bool = False) -> None:
    candidate = clean_candidate(candidate)
    lower = candidate.lower()
    if len(candidate) < 8 or len(candidate) > 180:
        return
    if lower.startswith(("however", "unfortunately", "without more information")):
        return
    if lower in {"those missing documents", "missing documents", "requesting those missing documents"}:
        return
    if is_vague_candidate(candidate):
        return

    has_signal = has_action_signal(candidate)
    has_object = contains_concrete_task_object(candidate)
    if not has_signal and not (allow_concrete_without_signal and has_object):
        return

    if candidate not in candidates:
        candidates.append(candidate)


def split_inline_task_candidates(fragment: str) -> list[str]:
    fragment = fragment.strip().rstrip(".")
    fragment = re.sub(r"^[:\s,]+", "", fragment)
    fragment = re.split(r"\.\s+", fragment, maxsplit=1)[0]
    fragment = fragment.replace(";", ",")
    fragment = re.sub(r",\s+and\s+", ", ", fragment)
    fragment = re.sub(r"\s+and\s+", ", ", fragment)
    return [clean_candidate(part) for part in fragment.split(",") if clean_candidate(part)]


def extract_inline_next_steps(line: str) -> list[str]:
    lower = line.lower()
    for marker in NEXT_STEP_MARKERS:
        marker_index = lower.find(marker)
        if marker_index != -1:
            fragment = line[marker_index + len(marker) :]
            return split_inline_task_candidates(fragment)
    return []


def add_keyword_gap_candidates(answer: str, candidates: list[str]) -> None:
    lower = answer.lower()
    has_pending_signal = any(signal in lower for signal in PENDING_TERMS)

    if "police report" in lower and has_pending_signal:
        add_candidate(candidates, "police report has not been received", allow_concrete_without_signal=True)
    if ("urgent care records" in lower or "urgent care record" in lower) and has_pending_signal:
        add_candidate(candidates, "urgent care records", allow_concrete_without_signal=True)
    if ("physical therapy notes" in lower or "physical therapy records" in lower or "pt records" in lower) and has_pending_signal:
        add_candidate(candidates, "physical therapy records", allow_concrete_without_signal=True)
    if "billing ledger" in lower and "urgent care" in lower and has_pending_signal:
        add_candidate(candidates, "urgent care billing ledger", allow_concrete_without_signal=True)
    if "available witness" in lower and "contact" in lower:
        add_candidate(candidates, "contacting the available witness")


def extract_task_candidates(answer: str) -> list[str]:
    candidates: list[str] = []
    capture_following_lines = False

    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if not line:
            capture_following_lines = False
            continue

        lower = line.lower()
        for candidate in extract_inline_next_steps(line):
            add_candidate(candidates, candidate, allow_concrete_without_signal=True)

        if lower.endswith("such as:") or lower.endswith("including:") or lower.endswith("for example:"):
            capture_following_lines = True
            continue

        bullet_match = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", line)
        if not capture_following_lines and bullet_match is None:
            continue

        candidate = bullet_match.group(1) if bullet_match else line
        add_candidate(candidates, candidate, allow_concrete_without_signal=capture_following_lines)

    add_keyword_gap_candidates(answer, candidates)
    return candidates[:8]
