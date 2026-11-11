from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from advisory import web
from advisory.ai import OpenAiStructuredClient
from advisory.job_preview import HeuristicJobIdentifier, OpenAiJobIdentifier
from advisory.practice import (
    DeterministicCardGenerator,
    GeneratedCard,
    GeneratedDeck,
    OpenAiCardGenerator,
    PracticeCard,
    deck_stats,
    new_cards,
    schedule,
)
from advisory.web import app

client = TestClient(app)
NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)
CV = "EXPERIENCE\n- Built Python services on Google Cloud for 2 million users.\nSKILLS\nPython, SQL"


def _card(box: int = 0, difficulty: int = 1) -> PracticeCard:
    return PracticeCard(id="c", question="Q?", difficulty=difficulty, box=box, due_at=NOW, created_at=NOW)  # type: ignore[arg-type]


def test_schedule_moves_cards_between_boxes() -> None:
    again = schedule(_card(box=3), "again", NOW)
    assert (again.box, again.due_at - NOW) == (0, timedelta(minutes=10))
    hard = schedule(_card(box=2), "hard", NOW)
    assert (hard.box, hard.due_at - NOW) == (2, timedelta(days=1, hours=12))
    good = schedule(_card(box=1), "good", NOW)
    assert (good.box, good.due_at - NOW, good.reviews, good.last_rating) == (2, timedelta(days=3), 1, "good")
    easy = schedule(_card(box=4), "easy", NOW)
    assert (easy.box, easy.due_at - NOW) == (5, timedelta(days=30))


def test_stats_suggest_the_next_level_once_mastered() -> None:
    assert deck_stats([], NOW)["suggested_level"] == 1
    level_one = [_card(box=4, difficulty=1) for _ in range(3)] + [_card(box=1, difficulty=1)]
    stats = deck_stats(level_one, NOW)
    assert stats["suggested_level"] == 2
    assert stats["levels"][0]["ready"] is True  # type: ignore[index]
    assert deck_stats([_card(box=1, difficulty=1)], NOW)["suggested_level"] == 1


def test_new_cards_skip_duplicates_and_respect_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    deck = GeneratedDeck(
        cards=[GeneratedCard(question="Q?"), GeneratedCard(question=" q "), GeneratedCard(question="R")]
    )
    created = new_cards(deck, 2, [_card()], NOW)
    assert [card.question for card in created] == ["R"]
    assert created[0].difficulty == 2 and created[0].due_at == NOW
    monkeypatch.setattr("advisory.practice.MAX_CARDS", 1)
    assert new_cards(deck, 1, [_card()], NOW) == []


def test_deterministic_generator_covers_each_level() -> None:
    generator = DeterministicCardGenerator()
    for level in (1, 2, 3):
        deck, _, _ = generator.generate(CV, "Python Kubernetes", level, 5, [])  # type: ignore[arg-type]
        assert deck.cards, level
    tough, _, _ = generator.generate(CV, "Python Kubernetes", 3, 5, [])
    assert any("kubernetes" in card.question.lower() for card in tough.cards)
    avoided, _, _ = generator.generate(CV, "", 1, 5, ["Walk me through your CV in two minutes."])
    assert all("Walk me through your CV" not in card.question for card in avoided.cards)


def _structured(payload: str, captured: list[dict[str, object]]) -> OpenAiStructuredClient:
    class Completions:
        def create(self, **kwargs: object) -> object:
            captured.append(kwargs)
            message = SimpleNamespace(content=payload, refusal=None)
            return SimpleNamespace(
                choices=[SimpleNamespace(finish_reason="stop", message=message)],
                usage=SimpleNamespace(prompt_tokens=80, completion_tokens=40),
            )

    return OpenAiStructuredClient(
        api_key="test",
        model="gpt-6-luna",
        reasoning_effort="low",
        max_output_tokens=6_000,
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )


def test_openai_card_generator_and_identifier_use_strict_schemas() -> None:
    captured: list[dict[str, object]] = []
    deck_json = GeneratedDeck(
        cards=[GeneratedCard(question="Why GKE?", key_points=["From CV"])]
    ).model_dump_json()
    deck, _, _ = OpenAiCardGenerator(_structured(deck_json, captured)).generate(CV, "Python", 3, 5, ["Old?"])
    assert deck.cards[0].question == "Why GKE?"
    assert "difficulty 3 of 3" in captured[0]["messages"][0]["content"]  # type: ignore[index]
    assert "- Old?" in captured[0]["messages"][0]["content"]  # type: ignore[index]
    identity, _, _ = OpenAiJobIdentifier(
        _structured('{"role": "AI Engineer", "company": "Acme"}', captured)
    ).identify("x" * 10_000)
    assert (identity.role, identity.company) == ("AI Engineer", "Acme")
    assert len(captured[1]["messages"][1]["content"]) < 6_100  # type: ignore[index]
    assert captured[1]["response_format"]["json_schema"]["strict"] is True  # type: ignore[index]


def test_heuristic_identifier_reads_role_and_company() -> None:
    identity, _, _ = HeuristicJobIdentifier().identify("Senior Data Engineer at Hooli\nRequirements: Python")
    assert (identity.role, identity.company) == ("Senior Data Engineer", "Hooli")
    nothing, _, _ = HeuristicJobIdentifier().identify("We are hiring!\nApply today")
    assert (nothing.role, nothing.company) == ("", "")


def _application(user: str) -> tuple[dict[str, str], dict[str, object]]:
    web.career_repository.clear()
    headers = {"x-advisory-user": user}
    version = client.post(
        "/api/cv-versions",
        headers=headers,
        data={"label": "CV"},
        files={"cv_file": ("cv.txt", CV.encode(), "text/plain")},
    ).json()
    application = client.post(
        "/api/applications",
        headers=headers,
        json={"company": "Acme", "role": "Engineer", "cv_version_id": version["id"]},
    ).json()
    return headers, application


def test_practice_api_generates_reviews_and_deletes_cards() -> None:
    headers, application = _application("practice-a")
    base = f"/api/applications/{application['id']}/practice"
    assert client.get(base, headers=headers).json()["stats"]["total"] == 0
    generated = client.post(f"{base}/generate", headers=headers, json={"difficulty": 1, "count": 3})
    assert generated.status_code == 200
    body = generated.json()
    assert body["added"] == 3 and body["stats"]["due"] == 3
    again = client.post(f"{base}/generate", headers=headers, json={"difficulty": 1, "count": 3}).json()
    assert {card["question"] for card in again["cards"][:3]} == {card["question"] for card in body["cards"]}

    card_id = body["cards"][0]["id"]
    reviewed = client.post(
        f"{base}/{card_id}/review", headers=headers, json={"rating": "good", "my_answer": " Mine "}
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["card"]["box"] == 1
    assert reviewed.json()["card"]["my_answer"] == "Mine"
    assert reviewed.json()["stats"]["due"] == again["stats"]["due"] - 1
    assert client.post(f"{base}/{card_id}/review", headers=headers, json={"rating": "meh"}).status_code == 422
    listed = client.get("/api/applications", headers=headers).json()[0]
    assert listed["practice_count"] == len(again["cards"])
    assert "practice_cards" not in listed

    other = {"x-advisory-user": "practice-intruder"}
    assert client.get(base, headers=other).status_code == 404
    assert client.delete(f"{base}/{card_id}", headers=headers).status_code == 200
    assert client.delete(f"{base}/{card_id}", headers=headers).status_code == 404
    assert client.post(f"{base}/missing/review", headers=headers, json={"rating": "good"}).status_code == 404


def test_practice_requires_a_cv_and_falls_back_on_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    headers, application = _application("practice-b")
    no_cv = client.post("/api/applications", headers=headers, json={"company": "B", "role": "R"}).json()
    assert (
        client.post(
            f"/api/applications/{no_cv['id']}/practice/generate", headers=headers, json={"difficulty": 1}
        ).status_code
        == 422
    )

    class Broken:
        def generate(self, *args: object) -> object:
            raise RuntimeError("down")

    monkeypatch.setattr(web, "card_generator", lambda: Broken())
    result = client.post(
        f"/api/applications/{application['id']}/practice/generate", headers=headers, json={"difficulty": 2}
    ).json()
    assert result["added"] >= 1
    assert "temporarily unavailable" in result["notice"]


def test_job_preview_endpoint_reads_text_and_files() -> None:
    headers, _ = _application("preview-a")
    assert client.post("/api/job-preview", headers=headers).status_code == 422
    from_text = client.post(
        "/api/job-preview", headers=headers, data={"job_text": "Staff ML Engineer at Initech\nPython"}
    ).json()
    assert (from_text["role"], from_text["company"], from_text["source"]) == (
        "Staff ML Engineer",
        "Initech",
        "text",
    )
    from_file = client.post(
        "/api/job-preview",
        headers=headers,
        files={"job_file": ("job.txt", b"Product Designer at Globex\nFigma", "text/plain")},
    ).json()
    assert (from_file["role"], from_file["source"]) == ("Product Designer", "file")
    bad = client.post(
        "/api/job-preview", headers=headers, files={"job_file": ("job.docx", b"PK", "application/zip")}
    )
    assert bad.status_code == 422


def test_job_preview_link_uses_page_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    headers, _ = _application("preview-b")
    from advisory.ingestion import JobPage

    class Fetcher:
        def fetch_page(self, url: str) -> JobPage:
            return JobPage(text="Python and Spark", role="Data Engineer", company="Hooli")

    monkeypatch.setattr(web, "job_description_fetcher", lambda: Fetcher())
    result = client.post(
        "/api/job-preview", headers=headers, data={"job_url": "https://jobs.example/1"}
    ).json()
    assert (result["role"], result["company"], result["source"]) == ("Data Engineer", "Hooli", "link")
