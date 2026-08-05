from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, Field

WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-/]{1,}")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it of on or our that the this to we will with you "
    "your".split()
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
        counts: dict[str, int] = {}
        first_index: dict[str, int] = {}
        for index, token in enumerate(self.tokens(job_text)):
            if len(token) < 3 or token in STOPWORDS:
                continue
            counts[token] = counts.get(token, 0) + 1
            first_index.setdefault(token, index)
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
