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
    assert terms == ["python", "security"]


def test_common_words_are_not_requirements() -> None:
    job = (
        "Building complex workflows for their applications while growing talent. Like building? "
        "Their growth matters. Building complex workflows. Requirements: Python, LangGraph, AWS. "
        "Our CEO and HR team offer PTO in the USA."
    )
    terms = MatchPolicy().extract_requirements(job)
    assert terms == ["python", "langgraph", "aws"]


def test_evidence_is_a_readable_sentence_when_pdf_text_is_fragmented() -> None:
    sentence = "Built agentic workflows with LangGraph and RAG on AWS for complex applications."
    fragmented = "\n".join(("EXPERIENCE " + sentence + " Led a team of four engineers.").split())
    result = MatchPolicy().assess(fragmented, "LangGraph RAG")
    assert result.requirements[0].evidence[0] == sentence


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


def test_matching_uses_whole_words_not_substrings() -> None:
    cv = "EXPERIENCE\nJavaScript developer on Linux who maintained trusted apps"
    result = MatchPolicy().assess(cv, "Java UX Rust AI")
    assert set(result.gaps) == {"java", "ux", "rust", "ai"}


def test_matching_recognises_common_variants() -> None:
    cv = (
        "EXPERIENCE\n- Designed secure REST services.\n"
        "- Led delivery and mentored five engineers.\n- Ran k8s on GCP."
    )
    result = MatchPolicy().assess(cv, "security leadership kubernetes google cloud")
    assert result.gaps == []
