from advisory.domain import MatchPolicy


def test_score_is_bounded_and_components_add_up() -> None:
    result = MatchPolicy().assess("EXPERIENCE\nPython\nSKILLS\nPython\nEDUCATION\nCS", "Python Kubernetes")
    assert 0 <= result.score <= 100
    assert result.score == sum(result.components.model_dump().values())


def test_matching_requires_literal_evidence() -> None:
    result = MatchPolicy().assess("EXPERIENCE\nBuilt Java services", "Python Kubernetes")
    assert result.gaps == ["python", "kubernetes"]
    assert all("if you have it" in recommendation for recommendation in result.recommendations)


def test_repeated_job_terms_rank_first() -> None:
    terms = MatchPolicy(max_requirements=2).extract_requirements("Python cloud Python security cloud Python")
    assert terms == ["python", "cloud"]


def test_requirement_extraction_prefers_meaningful_phrases() -> None:
    terms = MatchPolicy().extract_requirements(
        "We need a senior engineer with Google Cloud, machine learning, Python, and Terraform experience."
    )
    assert terms[:4] == ["google cloud", "machine learning", "python", "terraform"]
    assert not {"need", "senior", "engineer", "experience"}.intersection(terms)


def test_requirement_extraction_rejects_job_page_boilerplate() -> None:
    terms = MatchPolicy().extract_requirements(
        "Not What Who Forward Deployed Customer Data Services Build Business Code Learn "
        "Python AWS Kubernetes Terraform technical leadership"
    )
    assert terms == ["python", "aws", "kubernetes", "terraform", "technical leadership"]
    assert not {
        "not",
        "what",
        "who",
        "forward",
        "deployed",
        "customer",
        "data",
        "services",
        "build",
        "business",
        "code",
        "learn",
    }.intersection(terms)


def test_empty_job_is_safe() -> None:
    result = MatchPolicy().assess("EXPERIENCE", "")
    assert result.score <= 20
    assert result.band == "weak"
