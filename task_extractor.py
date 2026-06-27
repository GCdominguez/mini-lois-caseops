from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import ollama

ACTION_VERBS = (
    "request",
    "obtain",
    "acquire",
    "contact",
    "review",
    "collect",
    "follow up",
    "draft",
    "build",
    "prepare",
    "create",
    "search",
    "discuss",
    "inquire",
)

INLINE_ACTION_VERBS = (
    "request",
    "obtain",
    "acquire",
    "contact",
    "review",
    "collect",
    "follow up",
    "draft",
    "build",
    "prepare",
    "create",
    "search",
    "discuss",
)

TASK_OBJECT_TERMS = (
    "name",
    "contact",
    "record",
    "report",
    "ledger",
    "witness",
    "policy",
    "procedure",
    "guideline",
    "communication",
    "email",
    "document",
    "protocol",
    "template",
    "handbook",
    "review",
    "evaluation",
    "warning",
    "disciplinary",
    "payroll",
    "paycheck",
    "statement",
    "outline",
    "timeline",
    "complaint",
    "response",
    "letter",
    "agency",
    "database",
    "archive",
    "source",
    "nlrb",
    "court",
    "extension",
    "continuance",
    "summary",
    "concern",
)

PENDING_SIGNALS = (
    "missing",
    "not received",
    "not yet received",
    "hasn't been received",
    "has not been received",
    "never received",
    "not available",
    "not obtained",
    "incomplete",
    "need to",
    "needs to",
    "still need",
    "no evidence",
    "does not have",
    "not on file",
    "do not have",
    "don't have",
)

SECTION_MARKERS = (
    "such as:",
    "including:",
    "for example:",
    "next steps:",
    "actionable items:",
    "action items:",
    "recommended actions:",
    "need to know:",
    "we need to know:",
    "we should request:",
)

QUESTION_STARTERS = (
    "is there ",
    "are there ",
    "what are ",
    "what is ",
    "who is ",
    "who are ",
    "do we have ",
    "does the matter have ",
)

MATTER_WORKFLOW_QUESTION_TERMS = (
    "matter",
    "case",
    "client",
    "employer",
    "johnson",
    "alicia",
    "rideshare",
    "martinez",
    "luis",
    "record",
    "records",
    "document",
    "documents",
    "docs",
    "evidence",
    "missing",
    "gap",
    "gaps",
    "next",
    "action",
    "task",
    "risk",
    "status",
    "summary",
    "witness",
    "police",
    "medical",
    "billing",
    "pt",
    "urgent care",
    "claim",
    "defense",
    "liability",
    "treatment",
    "handbook",
    "performance",
    "warning",
    "payroll",
    "file",
    "source",
    "workflow",
    "discovery",
    "mediation",
    "pre-mediation",
    "phase",
    "move forward",
    "get out",
    "proceed",
    "representation",
    "represent",
    "attorney",
    "paralegal",
    "extension",
    "continuance",
)

SUPPRESSED_QUESTION_SIGNALS = (
    "what model",
    "model are you",
    "keys",
    "secrets",
    "api key",
    "password",
    "token",
    "system prompt",
    "instructions",
    "today",
    "current date",
    "what time",
    "poem",
    "story",
    "joke",
    "haiku",
    "song",
    "lighthouse",
    "my name is",
    "who am i",
    "where am i",
    "hello",
    "hi ",
    "hey",
    "quit my job",
    "doockie",
    "pookie",
    "poopy",
    "poop",
)

IRRELEVANT_ANSWER_SIGNALS = (
    "no relevant information provided",
    "no relevant information in the context",
    "no information provided in the context",
    "couldn't find any specific information",
    "cannot find any specific information",
    "question itself doesn't appear to be connected",
    "doesn't appear to be connected",
    "not connected to any of the provided information",
    "not relevant to this matter",
    "unrelated to this matter",
    "no connection to the matter",
    "no connection to matter",
    "no connection to the matter metadata",
)

CLARIFICATION_ANSWER_SIGNALS = (
    "not sure what question or topic",
    "i'm not sure what question",
    "please provide more context",
    "could you please provide more context",
    "please let me know how i can assist",
    "would you like me to",
    "which aspect of the matter you'd like to discuss",
)

STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "from",
    "have",
    "into",
    "more",
    "only",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "through",
    "with",
    "would",
    "could",
    "should",
    "request",
    "obtain",
    "acquire",
    "contact",
    "review",
    "collect",
    "follow",
    "draft",
    "build",
    "prepare",
    "create",
    "search",
    "discuss",
    "inquire",
}


def clean_text(text: str) -> str:
    text = str(text or "").strip()
    text = text.replace("**", "")
    text = re.sub(r"\s*\[[Ss]\d+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -•\t").rstrip(".?")


def answer_is_unrelated(answer: str) -> bool:
    lower = clean_text(answer).lower()
    return any(signal in lower for signal in IRRELEVANT_ANSWER_SIGNALS)


def answer_is_clarification(answer: str) -> bool:
    lower = clean_text(answer).lower()
    return any(signal in lower for signal in CLARIFICATION_ANSWER_SIGNALS)


def question_allows_task_extraction(question: Optional[str]) -> bool:
    if question is None:
        return True

    lower = clean_text(question).lower()
    if not lower:
        return True

    if any(signal in lower for signal in SUPPRESSED_QUESTION_SIGNALS):
        return False

    if not any(term in lower for term in MATTER_WORKFLOW_QUESTION_TERMS):
        return False

    return True


def should_extract_tasks(question: Optional[str], answer: str) -> bool:
    if not question_allows_task_extraction(question):
        return False
    if answer_is_unrelated(answer) or answer_is_clarification(answer):
        return False
    return True


def significant_terms(text: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", clean_text(text).lower())
    return {token for token in tokens if token not in STOPWORDS and len(token) >= 4}


def candidate_supported_by_answer(candidate: str, answer: str) -> bool:
    candidate_text = clean_text(candidate).lower()
    answer_text = clean_text(answer).lower()
    if not candidate_text or not answer_text:
        return False
    if candidate_text in answer_text:
        return True

    terms = significant_terms(candidate_text)
    if not terms:
        return False

    overlap = {term for term in terms if term in answer_text}
    required = 1 if len(terms) <= 2 else 2
    return len(overlap) >= required


def has_task_object(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in TASK_OBJECT_TERMS)


def has_action_signal(text: str) -> bool:
    lower = text.lower()
    return lower.startswith(ACTION_VERBS) or any(signal in lower for signal in PENDING_SIGNALS)


def is_question_gap(text: str) -> bool:
    lower = text.lower()
    return lower.startswith(QUESTION_STARTERS) and has_task_object(text)


def should_keep_candidate(text: str, *, section_context: bool = False) -> bool:
    text = clean_text(text)
    lower = text.lower()
    if len(text) < 8 or len(text) > 220:
        return False
    if lower.startswith(("however", "unfortunately", "without more information")):
        return False
    if any(vague in lower for vague in ("build a stronger case", "more information", "better understanding")):
        return False
    return has_action_signal(text) or is_question_gap(text) or (section_context and has_task_object(text))


def normalize_candidate(text: str) -> str:
    text = clean_text(text)
    if ":" in text:
        prefix = clean_text(text.split(":", 1)[0])
        if should_keep_candidate(prefix, section_context=True):
            return prefix
    return text


def add_candidate(candidates: List[str], text: str, *, section_context: bool = False) -> None:
    candidate = normalize_candidate(text)
    if should_keep_candidate(candidate, section_context=section_context) and candidate not in candidates:
        candidates.append(candidate)


def expand_compound_candidate(candidate: str) -> list[str]:
    text = normalize_candidate(candidate)
    lower = text.lower()
    expanded: list[str] = []

    if "record" in lower and "ledger" in lower:
        if "urgent care" in lower:
            expanded.append("obtain urgent care records")
            expanded.append("obtain urgent care billing ledger")
        else:
            expanded.append("obtain missing records")
            expanded.append("obtain billing ledger")
    elif "physical therapy" in lower and "urgent care" in lower and "record" in lower:
        expanded.append("obtain urgent care records")
        expanded.append("obtain physical therapy records")

    return expanded or [text]


def inline_action_candidates(line: str) -> list[str]:
    line = clean_text(line)
    lower = line.lower()
    if not any(re.search(rf"\b{re.escape(verb)}\b", lower) for verb in INLINE_ACTION_VERBS):
        return []

    candidates: list[str] = []
    clauses = re.split(r"\.\s+|;|\bor\b", line)
    for clause in clauses:
        clause = clean_text(clause)
        match = re.search(
            r"\b(request|obtain|acquire|contact|review|collect|follow up|draft|build|prepare|create|search|discuss)\b(.+)",
            clause,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        candidate = clean_text(match.group(0))
        for expanded in expand_compound_candidate(candidate):
            candidates.append(expanded)
    return candidates


def extract_rule_based_task_candidates(answer: str, question: Optional[str] = None) -> List[str]:
    if not should_extract_tasks(question, answer):
        return []

    candidates: List[str] = []
    section_mode = False
    captured_bullet = False

    for raw_line in answer.splitlines():
        line = clean_text(raw_line)
        if not line:
            continue

        lower = line.lower()
        if lower.endswith(SECTION_MARKERS):
            section_mode = True
            captured_bullet = False
            continue

        if "next steps" in lower and "include" in lower:
            section_mode = True
            captured_bullet = False
            after = re.split(r"include(?:s|d)?", line, maxsplit=1, flags=re.IGNORECASE)[-1]
            for part in re.split(r",|;| and ", after):
                add_candidate(candidates, part, section_context=True)
            continue

        for candidate in inline_action_candidates(line):
            add_candidate(candidates, candidate, section_context=True)

        bullet = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", line)
        if section_mode:
            if bullet:
                add_candidate(candidates, bullet.group(1), section_context=True)
                captured_bullet = True
                continue
            if captured_bullet:
                section_mode = False
                continue

        if bullet:
            add_candidate(candidates, bullet.group(1), section_context=False)

    return candidates[:8]


def parse_json_array(raw_text: str) -> List[Any]:
    raw_text = raw_text.strip()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("[")
        end = raw_text.rfind("]")
        if start == -1 or end <= start:
            return []
        try:
            parsed = json.loads(raw_text[start : end + 1])
        except json.JSONDecodeError:
            return []
    if isinstance(parsed, dict):
        parsed = parsed.get("task_candidates", [])
    return parsed if isinstance(parsed, list) else []


def extract_model_task_candidates(answer: str, model: Optional[str], question: Optional[str] = None) -> List[str]:
    if not model or not should_extract_tasks(question, answer):
        return []

    prompt = f"""
Read the user's question and assistant answer. Extract concrete legal/matter workflow tasks only when the user's question is about the selected matter or workflow.
Return only valid JSON: an array of short task strings.

Rules:
- If the question is casual, nonsense, a greeting, a current-date question, a creative-writing request, a model/security/secrets question, or otherwise not matter/workflow-related, return [].
- Extract only tasks that are directly stated in the answer.
- Extract tasks for records/documents to request, policies to review, people/agencies to contact, statements to draft, timelines to build, extensions/continuances to request, or databases to search.
- If missing info is written as a question, convert it into a task. Example: "Is there an employee handbook?" -> "Request employee handbook".
- Do not extract plain facts, completed items, symptoms, legal conclusions, clarification options, or vague advice.

Question:
{question or ""}

Answer:
{answer}
""".strip()

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0},
        )
    except Exception:
        return []

    parsed = parse_json_array(response["message"]["content"])
    candidates: List[str] = []
    for item in parsed:
        text = item if isinstance(item, str) else item.get("title") or item.get("task") if isinstance(item, dict) else ""
        for expanded in expand_compound_candidate(str(text)):
            if candidate_supported_by_answer(expanded, answer):
                add_candidate(candidates, expanded, section_context=True)
    return candidates


def extract_task_candidates(answer: str, model: Optional[str] = None, question: Optional[str] = None) -> List[str]:
    if not should_extract_tasks(question, answer):
        return []

    candidates: List[str] = []
    for candidate in extract_model_task_candidates(answer, model, question=question):
        add_candidate(candidates, candidate, section_context=True)
    for candidate in extract_rule_based_task_candidates(answer, question=question):
        add_candidate(candidates, candidate, section_context=True)
    return candidates[:8]


def task_title_from_candidate(candidate: str) -> str:
    text = normalize_candidate(candidate)
    lower = text.lower()

    if ("employer" in lower or "company" in lower) and "name" in lower and "contact" in lower:
        return "Request employer name and contact information"
    if "employee handbook" in lower or "handbook" in lower:
        return "Request employee handbook"
    if "performance" in lower and ("review" in lower or "evaluation" in lower) and "warning" in lower:
        return "Obtain performance reviews and written warnings"
    if "performance" in lower and ("review" in lower or "evaluation" in lower):
        return "Obtain performance review records"
    if "written warning" in lower or "disciplinary" in lower:
        return "Obtain written warnings and disciplinary records"
    if "payroll" in lower or "paycheck" in lower:
        return "Acquire payroll records"
    if "coworker" in lower and "statement" in lower:
        return "Draft coworker statement outline"
    if "timeline" in lower:
        return "Build timeline of complaints and supervisor responses"
    if "termination letter" in lower:
        return "Review termination letter"
    if "supervisor" in lower and "response" in lower:
        return "Review supervisor responses"
    if "workplace safety" in lower and ("policy" in lower or "procedure" in lower):
        return "Review workplace safety reporting policy"
    if "retaliation" in lower and "policy" in lower:
        return "Review anti-retaliation policy"
    if ("previous" in lower or "prior" in lower or "similar" in lower) and ("incident" in lower or "complaint" in lower):
        return "Review prior safety incidents and complaints"
    if "nlrb" in lower or "employment agenc" in lower:
        return "Contact NLRB or employment agency"
    if "database" in lower or "archive" in lower or "court" in lower:
        return "Search databases and court records"
    if "lead attorney" in lower or "dana cruz" in lower:
        return "Discuss potential sources with lead attorney"
    if "police report" in lower:
        return "Request police report"
    if "urgent care" in lower and "record" in lower:
        return "Request urgent care records"
    if "physical therapy" in lower or "pt record" in lower:
        return "Request PT records"
    if "billing ledger" in lower:
        return "Request urgent care billing ledger"
    if "witness" in lower:
        return "Contact available witness"
    if "insurance" in lower and ("policy" in lower or "coverage" in lower):
        return "Request insurance policy or coverage details"
    if "extension" in lower:
        return "Request extension of time"
    if "continuance" in lower:
        return "Request continuance of pre-mediation discovery"
    if "intake summary" in lower or "medical summary" in lower:
        return "Review intake and medical summaries"
    if "concern" in lower and "paralegal" in lower:
        return "Discuss representation concerns with paralegal"

    for verb in ACTION_VERBS:
        if lower.startswith(verb):
            return text[:1].upper() + text[1:]
    return f"Review {text[:1].lower()}{text[1:]}"


def reason_from_candidate(candidate: str) -> str:
    text = normalize_candidate(candidate)
    lower = text.lower()
    if any(signal in lower for signal in PENDING_SIGNALS):
        return "The matter answer identifies this as missing or incomplete information."
    if is_question_gap(text):
        return "The answer frames this as information to verify or collect."
    return f"Candidate extracted from matter answer: {text}."


def confidence_from_candidate(candidate: str) -> str:
    text = normalize_candidate(candidate)
    lower = text.lower()
    if any(signal in lower for signal in PENDING_SIGNALS):
        return "high"
    if lower.startswith(ACTION_VERBS):
        return "high"
    return "medium"


def build_task_candidate_objects(
    answer: str,
    sources: List[Dict[str, object]],
    model: Optional[str] = None,
    question: Optional[str] = None,
) -> List[Dict[str, object]]:
    if not should_extract_tasks(question, answer):
        return []

    source_refs = [source.get("source_id") for source in sources if source.get("source_id")]
    structured: List[Dict[str, object]] = []
    seen_titles = set()

    for candidate in extract_task_candidates(answer, model=model, question=question):
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
                "original_text": normalize_candidate(candidate),
            }
        )

    return structured
