from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, Field

WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-/]{1,}")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it of on or our that the this to we will with you "
    "your candidate candidates engineering engineer engineers experience experienced job looking need needs "
    "preferred required requirement requirements role senior strong team teams work working years".split()
)
BOILERPLATE_TERMS = frozenset(
    "about accept account all also apply benefits build business careers code company "
    "contact cookie cookies customer data deployed description details equal forward help home learn "
    "legal login more next not open page people policy privacy read save search service services share "
    "sign similar site support terms today view what where who why".split()
)
KNOWN_REQUIREMENT_TERMS = frozenset(
    "accessibility agile ai analytics architecture ats aws azure coaching communication compliance css "
    "cybersecurity django docker fastapi figma finops flask gcp git github golang graphql hadoop "
    "infrastructure java "
    "javascript kafka kubernetes langchain leadership llm mentoring microservices ml mongodb mysql node "
    "observability ownership postgresql product prototyping python pytorch react redis reliability "
    "research rust scalability scrum security spark sql stakeholder strategy tensorflow terraform "
    "testing typography typescript ux vue".split()
)
CURATED_PHRASES = (
    "artificial intelligence",
    "automated testing",
    "computer vision",
    "continuous delivery",
    "continuous integration",
    "cross-functional leadership",
    "customer experience",
    "data engineering",
    "data science",
    "distributed systems",
    "generative ai",
    "google cloud",
    "machine learning",
    "natural language processing",
    "people management",
    "project management",
    "retrieval augmented generation",
    "site reliability",
    "software architecture",
    "technical leadership",
    "user research",
)
SECTIONS = {
    "experience": ("experience", "employment", "work history"),
    "skills": ("skills", "technologies", "technical skills"),
    "education": ("education", "degree", "university"),
}


class Requirement(BaseModel):
    term: str
    evidence: list[str] = Field(default_factory=list)
    matched: bool


class ScoreComponents(BaseModel):
    requirement_coverage: int = Field(ge=0, le=70)
    document_structure: int = Field(ge=0, le=20)
    evidence_density: int = Field(ge=0, le=10)


class Assessment(BaseModel):
    schema_version: str = "1.0"
    scoring_version: str = "baseline-1"
    score: int = Field(ge=0, le=100)
    band: str
    components: ScoreComponents
    requirements: list[Requirement]
    gaps: list[str]
    recommendations: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class MatchPolicy:
    max_requirements: int = 12
    scoring_version: ClassVar[str] = "baseline-1"

    @staticmethod
    def tokens(text: str) -> list[str]:
        return [token.lower().strip(".-/") for token in WORD_RE.findall(text)]

    def extract_requirements(self, job_text: str) -> list[str]:
        job_lower = job_text.lower()
        counts: dict[str, int] = {}
        first_index: dict[str, int] = {}

        detected_phrases = [phrase for phrase in CURATED_PHRASES if phrase in job_lower]
        phrase_tokens = {token for phrase in detected_phrases for token in phrase.split()}
        for phrase in detected_phrases:
            counts[phrase] = job_lower.count(phrase)
            first_index[phrase] = job_lower.index(phrase)

        raw_tokens = WORD_RE.findall(job_text)
        normalized_tokens = [token.lower().strip(".-/") for token in raw_tokens]
        token_counts: dict[str, int] = {}
        for token in normalized_tokens:
            token_counts[token] = token_counts.get(token, 0) + 1

        for raw_token, token in zip(raw_tokens, normalized_tokens, strict=True):
            if (
                len(token) < 2
                or token in STOPWORDS
                or token in BOILERPLATE_TERMS
                or token in phrase_tokens
            ):
                continue
            is_acronym = raw_token.isupper() and raw_token.isalpha() and 2 <= len(raw_token) <= 8
            is_technical_shape = any(character in raw_token for character in "+#./-") or any(
                character.isdigit() for character in raw_token
            )
            is_meaningful = (
                token in KNOWN_REQUIREMENT_TERMS
                or is_acronym
                or is_technical_shape
                or (token_counts[token] >= 2 and len(token) >= 4)
            )
            if not is_meaningful:
                continue
            counts[token] = counts.get(token, 0) + 1
            first_index.setdefault(token, job_lower.find(token))
        ranked = sorted(counts, key=lambda token: (-counts[token], first_index[token], token))
        return ranked[: self.max_requirements]

    @staticmethod
    def _evidence(term: str, cv_text: str) -> list[str]:
        lines = [line.strip() for line in cv_text.splitlines() if line.strip()]
        return [line[:240] for line in lines if term.lower() in line.lower()][:3]

    def assess(self, cv_text: str, job_text: str) -> Assessment:
        terms = self.extract_requirements(job_text)
        requirements = []
        for term in terms:
            evidence = self._evidence(term, cv_text)
            requirements.append(Requirement(term=term, evidence=evidence, matched=bool(evidence)))
        matched = [item for item in requirements if item.matched]
        coverage = round(70 * len(matched) / len(requirements)) if requirements else 0
        cv_lower = cv_text.lower()
        section_hits = sum(any(alias in cv_lower for alias in aliases) for aliases in SECTIONS.values())
        structure = round(20 * section_hits / len(SECTIONS))
        evidence_density = min(10, sum(len(item.evidence) for item in matched) * 2)
        score = max(0, min(100, coverage + structure + evidence_density))
        gaps = [item.term for item in requirements if not item.matched]
        recommendations = [
            f"Add truthful evidence for the '{gap}' requirement, if you have it." for gap in gaps[:5]
        ]
        warnings = [
            "This is an explainable CV–job matching heuristic, not a prediction of a commercial ATS.",
            "Never add a skill or achievement that is not supported by your real experience.",
        ]
        band = "strong" if score >= 75 else "partial" if score >= 45 else "weak"
        return Assessment(
            score=score,
            band=band,
            components=ScoreComponents(
                requirement_coverage=coverage,
                document_structure=structure,
                evidence_density=evidence_density,
            ),
            requirements=requirements,
            gaps=gaps,
            recommendations=recommendations,
            warnings=warnings,
        )
