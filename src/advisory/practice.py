"""Interview practice cards: generated per application, reviewed with simple spaced repetition."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from advisory.ai import UNTRUSTED_DOCUMENTS_RULE, OpenAiStructuredClient, _strict_object
from advisory.domain import MatchPolicy

Difficulty = Literal[1, 2, 3]
Rating = Literal["again", "hard", "good", "easy"]
LEVEL_NAMES = {1: "Warm-up", 2: "Role-specific", 3: "Tough"}
LEVEL_BRIEFS = {
    1: "warm-up questions about the candidate's own background: walk-throughs of roles, projects, and "
    "motivation, answerable straight from the CV",
    2: "role-specific technical and behavioural questions tied to the job's requirements and the "
    "CV's evidence",
    3: "tough questions: probing the CV's gaps against the job, trade-offs and failure stories, deep "
    "technical follow-ups, and pressure questions an experienced hiring manager would ask",
}
BOX_INTERVALS = (timedelta(minutes=10), timedelta(days=1), timedelta(days=3), timedelta(days=7),
                 timedelta(days=14), timedelta(days=30))
MASTERED_BOX = 4
MAX_CARDS = 80
MAX_BATCH = 8
LEVEL_UP_SHARE = 0.7


class PracticeCard(BaseModel):
    id: str
    question: str = Field(max_length=300)
    key_points: list[str] = Field(default_factory=list, max_length=4)
    difficulty: Difficulty = 1
    box: int = Field(default=0, ge=0, le=len(BOX_INTERVALS) - 1)
    due_at: datetime
    reviews: int = Field(default=0, ge=0)
    last_rating: Rating | None = None
    my_answer: str = Field(default="", max_length=3_000)
    created_at: datetime

    @property
    def mastered(self) -> bool:
        return self.box >= MASTERED_BOX


class GeneratedCard(BaseModel):
    question: str = Field(max_length=300)
    key_points: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("question", mode="before")
    @classmethod
    def bound_question(cls, value: object) -> str:
        return " ".join(str(value).split())[:300]

    @field_validator("key_points", mode="before")
    @classmethod
    def bound_points(cls, value: object) -> list[str]:
        return [str(item)[:240] for item in value[:4]] if isinstance(value, list) else []


class GeneratedDeck(BaseModel):
    cards: list[GeneratedCard] = Field(default_factory=list, max_length=MAX_BATCH)

    @field_validator("cards", mode="before")
    @classmethod
    def bound_cards(cls, value: object) -> list[object]:
        return value[:MAX_BATCH] if isinstance(value, list) else []


DECK_SCHEMA = _strict_object(
    {
        "cards": {
            "type": "array",
            "items": _strict_object(
                {"question": {"type": "string"}, "key_points": {"type": "array", "items": {"type": "string"}}}
            ),
        }
    }
)


def _key(question: str) -> str:
    return " ".join(question.casefold().split()).rstrip("?.! ")


def new_cards(
    generated: GeneratedDeck, difficulty: Difficulty, existing: list[PracticeCard], now: datetime
) -> list[PracticeCard]:
    seen = {_key(card.question) for card in existing}
    created: list[PracticeCard] = []
    for item in generated.cards:
        key = _key(item.question)
        if not key or key in seen or len(existing) + len(created) >= MAX_CARDS:
            continue
        seen.add(key)
        created.append(
            PracticeCard(
                id=uuid4().hex,
                question=item.question,
                key_points=item.key_points,
                difficulty=difficulty,
                due_at=now,
                created_at=now,
            )
        )
    return created


def schedule(card: PracticeCard, rating: Rating, now: datetime) -> PracticeCard:
    """Leitner boxes: again resets, hard repeats sooner, good moves up one box, easy moves up two."""
    top = len(BOX_INTERVALS) - 1
    if rating == "again":
        box, wait = 0, BOX_INTERVALS[0]
    elif rating == "hard":
        box = card.box
        wait = max(BOX_INTERVALS[0], BOX_INTERVALS[box] / 2)
    else:
        box = min(top, card.box + (1 if rating == "good" else 2))
        wait = BOX_INTERVALS[box]
    return card.model_copy(
        update={"box": box, "due_at": now + wait, "reviews": card.reviews + 1, "last_rating": rating}
    )


def deck_stats(cards: list[PracticeCard], now: datetime) -> dict[str, object]:
    levels = []
    for level in (1, 2, 3):
        in_level = [card for card in cards if card.difficulty == level]
        mastered = sum(card.mastered for card in in_level)
        levels.append(
            {
                "level": level,
                "name": LEVEL_NAMES[level],
                "total": len(in_level),
                "mastered": mastered,
                "due": sum(card.due_at <= now for card in in_level),
                "ready": bool(in_level) and mastered / len(in_level) >= LEVEL_UP_SHARE,
            }
        )
    suggested = 1
    for item in levels:
        suggested = int(str(item["level"]))
        if not item["ready"]:
            break
    return {
        "total": len(cards),
        "due": sum(card.due_at <= now for card in cards),
        "mastered": sum(card.mastered for card in cards),
        "levels": levels,
        "suggested_level": suggested,
    }


class CardGenerator(Protocol):
    def generate(
        self, cv_text: str, job_text: str, difficulty: Difficulty, count: int, avoid: list[str]
    ) -> tuple[GeneratedDeck, int, int]: ...


class DeterministicCardGenerator:
    """Rule-based questions used locally and whenever the model is unavailable."""

    def generate(
        self, cv_text: str, job_text: str, difficulty: Difficulty, count: int, avoid: list[str]
    ) -> tuple[GeneratedDeck, int, int]:
        units = MatchPolicy.evidence_units(cv_text)
        assessment = MatchPolicy().assess(cv_text, job_text) if job_text.strip() else None
        matched = [item for item in (assessment.requirements if assessment else []) if item.matched]
        gaps = assessment.gaps if assessment else []
        cards: list[GeneratedCard] = []
        if difficulty == 1:
            cards.append(GeneratedCard(
                question="Walk me through your CV in two minutes.",
                key_points=[
                    "Start with your current role", "Pick two achievements", "End with why this role"
                ],
            ))
            cards.append(GeneratedCard(
                question="Why are you interested in this role?",
                key_points=["Link the role to your recent work", "Name one thing you want to learn"],
            ))
            for unit in units[:4]:
                if len(unit.split()) >= 5:
                    cards.append(GeneratedCard(
                        question=f'Tell me about this: "{unit[:140]}"',
                        key_points=["Context and your role", "What you did", "The result"],
                    ))
        elif difficulty == 2:
            for item in matched[:4]:
                cards.append(GeneratedCard(
                    question=f"How have you used {item.term} in your work?",
                    key_points=[
                        f'From your CV: "{item.evidence[0][:160]}"', "Explain a concrete decision you made"
                    ],
                ))
            for gap in gaps[:3]:
                cards.append(GeneratedCard(
                    question=f"The role needs {gap}. What is your experience with it?",
                    key_points=[
                        "Be honest about the gap", "Name the closest related experience", "How you'd ramp up"
                    ],
                ))
            cards.append(GeneratedCard(
                question="Which part of this role could you do well from day one, and what proves it?",
                key_points=["Pick one responsibility", "Point to a CV example", "Name the result"],
            ))
            cards.append(GeneratedCard(
                question="Describe a recent technical or work decision you made and the trade-offs.",
                key_points=["The options you considered", "Why you chose one", "What happened"],
            ))
            for unit in units[:3]:
                if len(unit.split()) >= 6:
                    cards.append(GeneratedCard(
                        question=f'How exactly did you do this: "{unit[:140]}"?',
                        key_points=["Your own steps", "Tools or methods", "What you'd improve"],
                    ))
        else:
            for gap in gaps[:3]:
                cards.append(GeneratedCard(
                    question=f"Your CV doesn't show {gap}. Why should we hire you over someone who has it?",
                    key_points=[
                        "Acknowledge it directly", "Show transferable evidence", "A concrete 30-day plan"
                    ],
                ))
            cards.append(GeneratedCard(
                question="Tell me about a project that failed. What would you do differently?",
                key_points=["A real example", "Your part in it", "What changed afterwards"],
            ))
            cards.append(GeneratedCard(
                question="What trade-off in a past project would you defend today, and why?",
                key_points=["The options", "The constraint that decided it", "The outcome"],
            ))
        avoid_keys = {_key(question) for question in avoid}
        fresh = [card for card in cards if _key(card.question) not in avoid_keys]
        return GeneratedDeck(cards=fresh[:count]), 0, 0


class OpenAiCardGenerator:
    def __init__(self, client: OpenAiStructuredClient) -> None:
        self.client = client

    def generate(
        self, cv_text: str, job_text: str, difficulty: Difficulty, count: int, avoid: list[str]
    ) -> tuple[GeneratedDeck, int, int]:
        avoid_list = "\n".join(f"- {question}" for question in avoid[:60]) or "- (none yet)"
        instructions = f"""You prepare interview flashcards for one candidate and one job.
{UNTRUSTED_DOCUMENTS_RULE}
Write {count} new cards at difficulty {difficulty} of 3: {LEVEL_BRIEFS[difficulty]}.
Each card: a question an interviewer would really ask (under 35 words), and 2-4 short key points a strong
answer should cover. Key points must come only from the CV (name the real project, tool, or result) or be
honest guidance when the CV lacks evidence (e.g. "Admit the gap; mention related X"). Never invent facts.
Do not repeat or rephrase these existing questions:
{avoid_list}
Write in the language of the CV."""
        job = f"\n\n<job_description>\n{job_text}\n</job_description>" if job_text.strip() else ""
        content, input_tokens, output_tokens = self.client.complete(
            instructions=instructions,
            documents=f"<cv>\n{cv_text}\n</cv>{job}",
            schema_name="practice_cards",
            schema=DECK_SCHEMA,
        )
        return GeneratedDeck.model_validate_json(content), input_tokens, output_tokens
