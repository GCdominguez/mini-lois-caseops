from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import ollama

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
    "procedure",
    "procedures",
    "guideline",
    "guidelines",
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
    "letter",
    "letters",
    "agency",
    "agencies",
    "database",
    "databases",
    "archive",
    "archives",
    "source",
    "sources",
    "nlrb",
    "court",
    "courts",
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
    "reach out",
    "reaching out",
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
    "search",
    "searching",
    "discuss",
    "discussing",
    "inquire",
    "inquiring",
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
    "no evidence",
    "does not have",
    "not on file",
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
    "we should request",
    "we should consider reviewing",
    "we need to know",
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


def extract_rule_based_task_candidates(answer: str) -> List[str]:
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

        if lower.endswith(ACTION_LIST_HEADERS) or lower.endswith(("such as:", "including:", "for example:", "request:", "information on:", "need to know:")):
            capture_following_lines = True
            continue

        bullet_match = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", line)
        if not capture_following_lines and bullet_match is None:
            continue

        candidate = bullet_match.group(1) if bullet_match else line
        add_candidate(candidates, candidate, allow_concrete_without_signal=capture_following_lines)

    add_keyword_gap_candidates(answer, candidates)
    return candidates[:8]


def _parse_json_array(raw_text: str) -> List[Any]:
    raw_text = raw_text.strip()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("[")
        end = raw_text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            parsed = json.loads(raw_text[start : end + 1])
        except json.JSONDecodeError:
            return []

    if isinstance(parsed, dict):
        parsed = parsed.get("task_candidates", [])
    return parsed if isinstance(parsed, list) else []


def extract_model_task_candidates(answer: str, model: Optional[str]) -> List[str]:
    if not model:
        return []

    prompt = f"""
You are extracting workflow task candidates from an AI-generated legal matter answer.

Return ONLY valid JSON: an array of strings.

Rules:
- Extract only concrete operational tasks someone could create in a matter record.
- Include tasks for missing documents, requested-but-not-received items, records to obtain, people to contact, statements to draft, timelines to build, policies/documents to review, agencies to contact, or databases to search.
- Do not extract plain facts, symptoms, background context, completed/uploaded items, legal conclusions, or vague advice.
- Prefer short task-like wording starting with a verb: Request, Obtain, Acquire, Contact, Draft, Build, Review, Prepare, Search, Discuss.
- Do not invent tasks that are not supported by the answer.
- Return [] if there are no actionable tasks.

Answer:
{answer}
""".strip()

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": "You extract task candidates and return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0},
        )
        content = response["message"]["content"]
    except Exception:
        return []

    parsed = _parse_json_array(content)
    candidates: List[str] = []
    for item in parsed:
        if isinstance(item, str):
            add_candidate(candidates, item, allow_concrete_without_signal=True)
        elif isinstance(item, dict):
            text = str(item.get("title") or item.get("task") or item.get("original_text") or "")
            add_candidate(candidates, text, allow_concrete_without_signal=True)
    return candidates


def extract_task_candidates(answer: str, model: Optional[str] = None) -> List[str]:
    candidates: List[str] = []

    for candidate in extract_model_task_candidates(answer, model):
        add_candidate(candidates, candidate, allow_concrete_without_signal=True)

    for candidate in extract_rule_based_task_candidates(answer):
        add_candidate(candidates, candidate, allow_concrete_without_signal=True)

    return candidates[:8]


def task_title_from_candidate(candidate: str) -> str:
    text = normalize_task_candidate(candidate)
    lower = text.lower()

    if "employee handbook" in lower:
        return "Request employee handbook"
    if "performance reviews" in lower and "written warnings" in lower:
        return "Obtain performance reviews and written warnings"
    if "performance reviews" in lower or "performance evaluation" in lower or "performance evaluations" in lower:
        return "Obtain performance reviews"
    if "written warnings" in lower or "disciplinary action" in lower or "disciplinary actions" in lower:
        return "Obtain written warnings and disciplinary records"
    if "payroll" in lower or "paycheck" in lower:
        return "Acquire payroll records"
    if "coworker statement" in lower or "statement outline" in lower:
        return "Draft coworker statement outline"
    if "timeline" in lower and ("complaint" in lower or "supervisor" in lower):
        return "Build timeline of complaints and supervisor responses"
    if "termination letter" in lower:
        return "Review termination letter"
    if "supervisor responses" in lower or "supervisor response" in lower:
        return "Review supervisor responses"
    if "workplace safety" in lower and ("policy" in lower or "policies" in lower):
        return "Review workplace safety reporting policy"
    if "retaliation" in lower and ("policy" in lower or "policies" in lower):
        return "Review anti-retaliation policy"
    if "previous incidents" in lower or "prior incidents" in lower or "complaints related" in lower or "similar safety concerns" in lower:
        return "Review prior safety incidents and complaints"
    if "nlrb" in lower or "state/local employment" in lower or "employment agencies" in lower:
        return "Contact NLRB or employment agency"
    if "online databases" in lower or "news archives" in lower or "court records" in lower:
        return "Search databases and court records"
    if "dana cruz" in lower or "lead attorney" in lower:
        return "Discuss potential sources with lead attorney"
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
    if "company polic" in lower or "company handbook" in lower:
        return "Review company policies and procedures"

    gerunds = {
        "requesting ": "Request ",
        "obtaining ": "Obtain ",
        "acquiring ": "Acquire ",
        "contacting ": "Contact ",
        "reaching out ": "Contact ",
        "reviewing ": "Review ",
        "collecting ": "Collect ",
        "following up on ": "Follow up on ",
        "drafting ": "Draft ",
        "building ": "Build ",
        "preparing ": "Prepare ",
        "creating ": "Create ",
        "searching ": "Search ",
        "discussing ": "Discuss ",
        "inquiring ": "Inquire ",
    }
    for prefix, replacement in gerunds.items():
        if lower.startswith(prefix):
            return replacement + text[len(prefix) :]
    if lower.startswith(ACTION_TERMS):
        return text[:1].upper() + text[1:]
    return f"Review {text[:1].lower()}{text[1:]}"


def reason_from_candidate(candidate: str) -> str:
    cleaned = normalize_task_candidate(candidate)
    lower = cleaned.lower()
    if "not received" in lower or "not yet received" in lower or "has not been received" in lower:
        return "The matter context indicates this item has not been received."
    if "incomplete" in lower or "not available" in lower or "missing" in lower or "never received" in lower or "no evidence" in lower or "not on file" in lower:
        return "The matter context indicates this information is missing or incomplete."
    if "witness" in lower:
        return "The matter context identifies an available witness who may need follow-up."
    return f"Candidate extracted from matter answer: {cleaned}."


def confidence_from_candidate(candidate: str) -> str:
    lower = candidate.lower()
    if any(term in lower for term in ("not received", "not yet received", "missing", "incomplete", "not available", "never received", "no evidence", "not on file")):
        return "high"
    if lower.startswith(ACTION_TERMS):
        return "high"
    return "medium"


def build_task_candidate_objects(answer: str, sources: List[Dict[str, object]], model: Optional[str] = None) -> List[Dict[str, object]]:
    source_refs = [source.get("source_id") for source in sources if source.get("source_id")]
    structured: List[Dict[str, object]] = []
    seen_titles = set()

    for candidate in extract_task_candidates(answer, model=model):
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
