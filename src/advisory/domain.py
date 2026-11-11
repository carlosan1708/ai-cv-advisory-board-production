from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, Field

WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-/]{1,}")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it of on or our that the this to we will with you "
    "your candidate candidates engineering engineer engineers experience experienced job looking need needs "
    "preferred required requirement requirements role senior strong team teams work working years "
    "ability able across based best deliver delivering develop developing ensure environment including join "
    "knowledge level make must need needs new opportunity plus range responsibilities responsible skills "
    "solutions using well within".split()
)
BOILERPLATE_TERMS = frozenset(
    "about accept account all also apply benefits build business careers code company "
    "contact cookie cookies customer data deployed description details equal forward help home learn "
    "legal login more next not open page people policy privacy read save search service services share "
    "sign similar site support terms today view what where who why".split()
)
KNOWN_REQUIREMENT_TERMS = frozenset(
    "accessibility agile agents agentic ai airflow analytics android angular ansible api apis architecture "
    "ats aws azure bash bigquery budgeting c# c++ cassandra ci/cd cloudformation coaching communication "
    "compliance css cybersecurity dashboards databricks datadog dbt devops django docker dynamodb "
    "elasticsearch embeddings etl excel experimentation fastapi figma finops flask flutter forecasting "
    "gcp git github gitlab golang grafana graphql grpc hadoop helm hiring html hubspot ios java javascript "
    "jenkins jira kafka keras kotlin kubernetes lambda langchain langgraph leadership linux llm llmops "
    "llms looker marketing mentoring microservices ml mlops mongodb mysql negotiation next.js nlp node "
    "node.js numpy observability onboarding openai oracle ownership pandas php postgres postgresql "
    "powerbi prometheus prototyping pulumi python pytorch rabbitmq rag react redis redshift reliability "
    "research roadmap ruby rust salesforce sap scala scalability scikit-learn scrum security seo snowflake "
    "spark splunk spring sql stakeholder stakeholders statistics strategy swift tableau tensorflow "
    "terraform testing typescript typography ux vue".split()
)
ACRONYM_STOPLIST = frozenset(
    "ceo cto cfo coo eeo eoe hr pto usa us uk eu emea apac latam faq ok id inc llc ltd co etc "
    "am pm est pst cet utc ny sf la".split()
)
CURATED_PHRASES = (
    "a/b testing",
    "agent orchestration",
    "artificial intelligence",
    "automated testing",
    "cloud infrastructure",
    "code review",
    "data pipelines",
    "data visualization",
    "deep learning",
    "event-driven architecture",
    "fine-tuning",
    "infrastructure as code",
    "large language models",
    "prompt engineering",
    "react native",
    "system design",
    "tool calling",
    "vector databases",
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
TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "ai": ("ai", "artificial intelligence", "machine learning", "llm", "generative ai"),
    "artificial intelligence": ("artificial intelligence", "ai"),
    "machine learning": ("machine learning", "ml"),
    "ml": ("ml", "machine learning"),
    "llm": ("llm", "large language model", "generative ai"),
    "security": ("security", "secure", "secured", "securing", "cybersecurity"),
    "cybersecurity": ("cybersecurity", "security"),
    "leadership": ("leadership", "led", "lead", "leading", "mentored", "mentoring", "managed", "coached"),
    "mentoring": ("mentoring", "mentored", "mentor", "coached", "coaching"),
    "coaching": ("coaching", "coached", "mentored", "mentoring"),
    "testing": ("testing", "tests", "tested", "test automation", "pytest", "jest"),
    "automated testing": ("automated testing", "automated tests", "test automation"),
    "kubernetes": ("kubernetes", "k8s", "gke", "eks", "aks"),
    "google cloud": ("google cloud", "gcp"),
    "gcp": ("gcp", "google cloud"),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure",),
    "postgresql": ("postgresql", "postgres"),
    "javascript": ("javascript", "js"),
    "node": ("node", "node.js", "nodejs"),
    "golang": ("golang", "go language"),
    "communication": ("communication", "communicated", "communicating", "presented", "presenting"),
    "stakeholder": ("stakeholder", "stakeholders"),
    "ownership": ("ownership", "owned", "owner"),
    "architecture": ("architecture", "architected", "architectural"),
    "observability": ("observability", "monitoring", "tracing", "alerting"),
    "continuous integration": ("continuous integration", "ci/cd", "ci"),
    "continuous delivery": ("continuous delivery", "continuous deployment", "ci/cd", "cd"),
    "people management": ("people management", "managed a team", "direct reports", "line manager"),
    "technical leadership": ("technical leadership", "tech lead", "technical lead"),
    "user research": ("user research", "usability testing", "user interviews"),
}
BULLET_CHARS = " -\u2022*\t"
HEADING_PREFIX_RE = re.compile(r"^(?:[A-Z][A-Z&/]{3,}\s+)+(?=[A-Z][a-z])")
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
    scoring_version: str = "baseline-3"
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
    scoring_version: ClassVar[str] = "baseline-3"

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
            is_acronym = (
                raw_token.isupper()
                and raw_token.isalpha()
                and 2 <= len(raw_token) <= 6
                and token not in ACRONYM_STOPLIST
            )
            is_technical_shape = (
                any(character in raw_token for character in "+#")
                or bool(re.fullmatch(r"[a-z]+\.(js|ts|net|io)", token))
                or (
                    any(character.isdigit() for character in raw_token)
                    and any(character.isalpha() for character in raw_token)
                )
            )
            is_meaningful = token in KNOWN_REQUIREMENT_TERMS or is_acronym or is_technical_shape
            if not is_meaningful:
                continue
            counts[token] = counts.get(token, 0) + 1
            first_index.setdefault(token, job_lower.find(token))
        ranked = sorted(counts, key=lambda token: (-counts[token], first_index[token], token))
        return ranked[: self.max_requirements]

    @staticmethod
    def term_pattern(term: str) -> re.Pattern[str]:
        """Whole-word match for a requirement or any alias, tolerating plurals and space/hyphen variants."""
        alternatives = []
        for alias in TERM_ALIASES.get(term.lower(), (term.lower(),)):
            parts = [re.escape(part) for part in re.split(r"[\s\-]+", alias) if part]
            alternatives.append(r"[\s\-]+".join(parts))
        body = "|".join(sorted(alternatives, key=len, reverse=True))
        return re.compile(rf"(?<![a-z0-9])(?:{body})(?:s|es)?(?![a-z0-9])", re.IGNORECASE)

    @staticmethod
    def evidence_units(cv_text: str) -> list[str]:
        """Readable CV statements: real lines, or sentences rebuilt when a PDF split text into fragments."""
        lines = [line.strip(BULLET_CHARS) for line in cv_text.splitlines() if line.strip(BULLET_CHARS)]
        if not lines:
            return []
        short = sum(len(line.split()) <= 2 for line in lines)
        if len(lines) < 15 or short / len(lines) <= 0.6:
            return lines
        flowing = " ".join(" ".join(lines).split())
        parts = re.split(r"(?<=[.;!?])\s+|\s+[\u2022\u25aa\u25cf\u25e6\u2013|]\s+", flowing)
        units: list[str] = []
        for part in parts:
            words = part.split()
            for start in range(0, len(words), 30):
                chunk = " ".join(words[start : start + 30]).strip(BULLET_CHARS)
                chunk = HEADING_PREFIX_RE.sub("", chunk)
                if chunk:
                    units.append(chunk)
        return units

    @classmethod
    def _evidence(cls, term: str, cv_text: str) -> list[str]:
        pattern = cls.term_pattern(term)
        return [unit[:240] for unit in cls.evidence_units(cv_text) if pattern.search(unit)][:3]

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
