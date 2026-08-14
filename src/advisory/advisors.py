from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Advisor:
    id: str
    initials: str
    name: str
    role: str
    focus: str


ADVISORS = (
    Advisor(
        "recruiter",
        "TR",
        "Technical Recruiter",
        "Positioning & ATS",
        "role alignment, searchable language, clarity, and unsupported claims",
    ),
    Advisor(
        "hiring_manager",
        "HM",
        "Hiring Manager",
        "Impact & seniority",
        "scope, ownership, outcomes, seniority signals, and business relevance",
    ),
    Advisor(
        "technical",
        "TE",
        "Technical Reviewer",
        "Depth & credibility",
        "technical depth, architecture, delivery evidence, and interview defensibility",
    ),
    Advisor(
        "executive",
        "EB",
        "Executive Story Editor",
        "Leadership narrative",
        "strategic influence, executive clarity, transformation, and stakeholder leadership",
    ),
    Advisor(
        "impact",
        "IR",
        "Impact & ROI Reviewer",
        "Results & metrics",
        "measurable outcomes, scale, cost, revenue, risk reduction, and missing context",
    ),
    Advisor(
        "startup",
        "SP",
        "Startup Product Leader",
        "Ownership & adaptability",
        "ambiguity, speed, product judgment, cross-functional ownership, and resourcefulness",
    ),
)

ADVISOR_BY_ID = {advisor.id: advisor for advisor in ADVISORS}
DEFAULT_ADVISOR_IDS = ("recruiter", "hiring_manager", "technical")
MAX_ADVISORS = 3


def normalize_advisor_ids(raw_ids: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    for raw_id in raw_ids or DEFAULT_ADVISOR_IDS:
        advisor_id = raw_id.strip()
        if advisor_id in ADVISOR_BY_ID and advisor_id not in normalized:
            normalized.append(advisor_id)
    return normalized[:MAX_ADVISORS] or list(DEFAULT_ADVISOR_IDS)


def advisor_context(advisor_ids: list[str] | tuple[str, ...] | None = None) -> list[dict[str, str]]:
    return [asdict(ADVISOR_BY_ID[item]) for item in normalize_advisor_ids(advisor_ids)]
