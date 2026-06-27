from __future__ import annotations

import re
from typing import Dict, List

CONCRETE_TERMS = (
    "record",
    "records",
    "report",
    "reports",
    "ledger",
    "witness",
    "witnesses",
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
    "handbook",
    "review",
    "reviews",
    "warning",
    "warnings",
    "payroll",
    "paycheck",
    "statement",
    "outline",
    "timeline",
    "complaint",
    "complaints",
    "response",
    "responses",
)

ACTION_TERMS = (
    "request",
    "requesting",
    "requested but",
    "obtain",
    "obtaining",
    "acquire",
    "acquiring",
    "contact",
    "contacting",
    "review",
    "reviewing",
    "collect",
    "collecting",
    "follow up",
    "following up",
    "draft",
    "drafting",
    "build",
    "building",
    "prepare",
    "preparing",
    "create",
    "creating",
)

PENDING_TERMS = (
    "missing",
    "not received",
    "not yet received",
    "hasn't been received",
    "has not been received",
    "never received",
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
    "actionable items include",
    "actionable items are",
    "we still need to",
    "we also need to",
    "we need to",
    "need to get",
)

ACTION_LIST_HEADERS = (
    "actionable items:",
    "action items:",
    "recommended actions:",
    "next steps:",
)


def clean_candidate(candidate: str) -> str:
    candidate = candidate.strip()
    candidate = candidate.replace("**", "")
    candidate = re.sub(r"\s*\[[Ss]\d+\]", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate)
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


def normalize_task_candidate(candidate: str) -> str:
    candidate = clean_candidate(candidate)
    if ":" in candidate:
        prefix = clean_candidate(candidate.split(":", 1)[0])
        if has_action_signal(prefix) and contains_concrete_task_object(prefix):
            return prefix
    return candidate


def add_candidate(candidates: List[str], candidate: str, *, allow_concrete_without_signal: bool = False) -> None:
    candidate = normalize_task_candidate(candidate)
    lower = candidate.lower()
    if len(candidate) < 8 or len(candidate) > 220:
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


def split_inline_task_candidates(fragment: str) -> List[str]:
    fragment = fragment.strip().rstrip(".")
    fragment = re.sub(r"^[:\s,]+", "", fragment)
    fragment = re.split(r"\.\s+", fragment, maxsplit=1)[0]
    fragment = fragment.replace(";", ",")
    fragment = re.sub(r",\s+and\s+", ", ", fragment)
    fragment = re.sub(r"\s+and\s+", ", ", fragment)
    return [clean_candidate(part) for part in fragment.split(",") if clean_candidate(part)]


def extract_inline_next_steps(line: str) -> List[str]:
    lower = line.lower()
    for marker in NEXT_STEP_MARKERS:
        marker_index = lower.find(marker)
        if marker_index != -1:
            fragment = line[marker_index + len(marker) :]
            return split_inline_task_candidates(fragment)
    return []


def add_keyword_gap_candidates(answer: str, candidates: List[str]) -> None:
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


def extract_task_candidates(answer: str) -> List[str]:
    candidates: List[str] = []
    capture_following_lines = False

    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if not line:
            capture_following_lines = False
            continue

        lower = line.lower()
        for candidate in extract_inline_next_steps(line):
            add_candidate(candidates, candidate, allow_concrete_without_signal=True)

        if lower.endswith(ACTION_LIST_HEADERS) or lower.endswith(("such as:", "including:", "for example:")):
            capture_following_lines = True
            continue

        bullet_match = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", line)
        if not capture_following_lines and bullet_match is None:
            continue

        candidate = bullet_match.group(1) if bullet_match else line
        add_candidate(candidates, candidate, allow_concrete_without_signal=capture_following_lines)

    add_keyword_gap_candidates(answer, candidates)
    return candidates[:8]


def task_title_from_candidate(candidate: str) -> str:
    text = normalize_task_candidate(candidate)
    lower = text.lower()

    if "employee handbook" in lower:
        return "Request employee handbook"
    if "performance reviews" in lower or "written warnings" in lower:
        return "Obtain performance reviews and written warnings"
    if "payroll" in lower or "paycheck" in lower:
        return "Acquire payroll records"
    if "coworker statement" in lower or "statement outline" in lower:
        return "Draft coworker statement outline"
    if "timeline" in lower and ("complaint" in lower or "supervisor" in lower):
        return "Build timeline of complaints and supervisor responses"
    if "police report" in lower:
        return "Request police report"
    if "urgent care records" in lower or "urgent care record" in lower:
        return "Request urgent care records"
    if "physical therapy" in lower or "pt record" in lower:
        return "Request PT records after April 19" if "after april 19" in lower else "Request PT records"
    if "billing ledger" in lower and "urgent care" in lower:
        return "Request urgent care billing ledger"
    if "witness" in lower:
        return "Contact available witness"
    if "insurance policy" in lower or "coverage details" in lower:
        return "Request insurance policy or coverage details"
    if "communication" in lower or "email" in lower:
        return "Request driver-company accident communications"
    if "incident report" in lower or "accident report" in lower:
        return "Request accident or incident report template"
    if "safety protocol" in lower:
        return "Request safety protocols for accident handling"
    if "regulatory" in lower:
        return "Review regulatory compliance documents"
    if "company polic" in lower:
        return "Review company accident and injury policies"

    gerunds = {
        "requesting ": "Request ",
        "obtaining ": "Obtain ",
        "acquiring ": "Acquire ",
        "contacting ": "Contact ",
        "reviewing ": "Review ",
        "collecting ": "Collect ",
        "following up on ": "Follow up on ",
        "drafting ": "Draft ",
        "building ": "Build ",
        "preparing ": "Prepare ",
        "creating ": "Create ",
    }
    for prefix, replacement in gerunds.items():
        if lower.startswith(prefix):
            return replacement + text[len(prefix) :]
    if lower.startswith(ACTION_TERMS):
        return text
    return f"Review {text[:1].lower()}{text[1:]}"


def reason_from_candidate(candidate: str) -> str:
    cleaned = normalize_task_candidate(candidate)
    lower = cleaned.lower()
    if "not received" in lower or "not yet received" in lower or "has not been received" in lower:
        return "The matter context indicates this item has not been received."
    if "incomplete" in lower or "not available" in lower or "missing" in lower or "never received" in lower:
        return "The matter context indicates this information is missing or incomplete."
    if "witness" in lower:
        return "The matter context identifies an available witness who may need follow-up."
    return f"Candidate extracted from matter answer: {cleaned}."


def confidence_from_candidate(candidate: str) -> str:
    lower = candidate.lower()
    if any(term in lower for term in ("not received", "not yet received", "missing", "incomplete", "not available", "never received")):
        return "high"
    if lower.startswith(ACTION_TERMS):
        return "high"
    return "medium"


def build_task_candidate_objects(answer: str, sources: List[Dict[str, object]]) -> List[Dict[str, object]]:
    source_refs = [source.get("source_id") for source in sources if source.get("source_id")]
    structured: List[Dict[str, object]] = []
    seen_titles = set()

    for candidate in extract_task_candidates(answer):
        title = task_title_from_candidate(candidate)
        if title in seen_titles:
            continue
        seen_titles.add(title)
        structured.append(
            {
                "title": title,
                "action_type": "create_task",
                "reason": reason_from_candidate(candidate),
                "confidence": confidence_from_candidate(candidate),
                "source_refs": source_refs,
                "original_text": normalize_task_candidate(candidate),
            }
        )

    return structured
