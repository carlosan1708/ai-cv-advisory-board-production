from __future__ import annotations

from typing import Any

import httpx
import pytest

from advisory import ingestion
from advisory.ingestion import (
    CvDocumentError,
    CvDocumentParser,
    JobDescriptionError,
    JobDescriptionFetcher,
    extract_job_description,
)


def test_text_cv_accepts_utf8_bom_and_normalizes_lines() -> None:
    parser = CvDocumentParser()
    result = parser.parse("resume.TXT", b"\xef\xbb\xbfEXPERIENCE\r\nBuilt Python systems")
    assert result == "EXPERIENCE\nBuilt Python systems"


@pytest.mark.parametrize(
    ("filename", "payload", "message"),
    [
        ("resume.docx", b"content", "not supported"),
        ("resume.txt", b"", "empty"),
        ("resume.txt", b"\xff\xfe", "UTF-8"),
        ("resume.pdf", b"not a pdf", "not a valid PDF"),
    ],
)
def test_cv_rejects_unsupported_or_unreadable_files(filename: str, payload: bytes, message: str) -> None:
    with pytest.raises(CvDocumentError, match=message):
        CvDocumentParser().parse(filename, payload)


def test_cv_rejects_oversized_file_and_extracted_text() -> None:
    with pytest.raises(CvDocumentError, match="larger than"):
        CvDocumentParser(max_file_bytes=3).parse("resume.txt", b"four")
    with pytest.raises(CvDocumentError, match="longer than"):
        CvDocumentParser(max_chars=3).parse("resume.txt", b"four")


def test_pdf_cv_extracts_each_page(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        is_encrypted = False
        pages = [FakePage("EXPERIENCE"), FakePage("Built Python services")]

    monkeypatch.setattr(ingestion, "PdfReader", lambda _: FakeReader())
    assert CvDocumentParser().parse("resume.pdf", b"%PDF-fake") == "EXPERIENCE\nBuilt Python services"


def test_pdf_cv_rejects_locked_blank_and_overlong_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    class LockedReader:
        is_encrypted = True
        pages: list[Any] = []

        @staticmethod
        def decrypt(_: str) -> int:
            return 0

    monkeypatch.setattr(ingestion, "PdfReader", lambda _: LockedReader())
    with pytest.raises(CvDocumentError, match="Password-protected"):
        CvDocumentParser().parse("resume.pdf", b"%PDF-fake")

    class BlankPage:
        @staticmethod
        def extract_text() -> str:
            return ""

    class BlankReader:
        is_encrypted = False
        pages = [BlankPage()]

    monkeypatch.setattr(ingestion, "PdfReader", lambda _: BlankReader())
    with pytest.raises(CvDocumentError, match="No readable text"):
        CvDocumentParser().parse("resume.pdf", b"%PDF-fake")

    class LongReader:
        is_encrypted = False
        pages = [BlankPage(), BlankPage()]

    monkeypatch.setattr(ingestion, "PdfReader", lambda _: LongReader())
    with pytest.raises(CvDocumentError, match="more than 1 pages"):
        CvDocumentParser(max_pdf_pages=1).parse("resume.pdf", b"%PDF-fake")


def test_job_extraction_prefers_jobposting_json_ld() -> None:
    html = """
    <html><body><main>Navigation fallback</main>
    <script type="application/ld+json">
      {"@type":"JobPosting","description":"<p>Build Python APIs</p><p>Lead delivery</p>"}
    </script></body></html>
    """
    assert extract_job_description(html) == "Build Python APIs\nLead delivery"


def test_job_extraction_supports_common_job_container_and_main_fallback() -> None:
    preferred = '<div class="description__text"><h2>Role</h2><p>Build services<br>Lead teams</p></div>'
    assert extract_job_description(preferred) == "Role\nBuild services\nLead teams"
    assert extract_job_description("<main><h1>Engineer</h1><p>Own Python systems</p></main>") == (
        "Engineer\nOwn Python systems"
    )


def public_fetcher(**overrides: Any) -> JobDescriptionFetcher:
    return JobDescriptionFetcher(
        resolver=lambda _: ["93.184.216.34"],
        **overrides,
    )


def test_job_fetcher_reads_public_html_and_plain_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/html":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<main><h1>Platform Engineer</h1><p>Build Python APIs</p></main>",
            )
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="Lead cloud delivery")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert "Build Python APIs" in public_fetcher().fetch("https://jobs.example/html", client=client)
        assert public_fetcher().fetch("https://jobs.example/plain", client=client) == "Lead cloud delivery"


@pytest.mark.parametrize(
    "url",
    [
        "http://jobs.example/role",
        "https://user:pass@jobs.example/role",
        "https://jobs.example:8443/role",
    ],
)
def test_job_fetcher_rejects_unsafe_url_shapes(url: str) -> None:
    with pytest.raises(JobDescriptionError):
        public_fetcher().fetch(url, client=httpx.Client(transport=httpx.MockTransport(lambda _: None)))


def test_job_fetcher_rejects_private_resolution_before_request() -> None:
    requested = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(200, text="should not be reached")

    fetcher = JobDescriptionFetcher(resolver=lambda _: ["127.0.0.1"])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JobDescriptionError, match="public"):
            fetcher.fetch("https://internal.example/job", client=client)
    assert requested is False


def test_job_fetcher_revalidates_every_redirect() -> None:
    def resolver(hostname: str) -> list[str]:
        return ["10.0.0.8"] if hostname == "internal.example" else ["93.184.216.34"]

    transport = httpx.MockTransport(
        lambda _: httpx.Response(302, headers={"location": "https://internal.example/job"})
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(JobDescriptionError, match="public"):
            JobDescriptionFetcher(resolver=resolver).fetch("https://jobs.example/redirect", client=client)


def test_job_fetcher_rejects_connected_peer_outside_validated_dns_set() -> None:
    class FakeStream:
        @staticmethod
        def get_extra_info(_: str) -> tuple[str, int]:
            return ("10.0.0.9", 443)

    response = httpx.Response(
        200,
        headers={"content-type": "text/html"},
        text="<main>Python engineer</main>",
        extensions={"network_stream": FakeStream()},
    )
    with pytest.raises(JobDescriptionError, match="unexpected network"):
        public_fetcher()._validate_connected_peer(
            response,
            frozenset({"93.184.216.34"}),
            required=True,
        )


def test_job_fetcher_limits_redirects_size_and_content_type() -> None:
    redirect = httpx.MockTransport(lambda _: httpx.Response(302, headers={"location": "/again"}))
    with httpx.Client(transport=redirect) as client:
        with pytest.raises(JobDescriptionError, match="redirected too many"):
            public_fetcher(max_redirects=1).fetch("https://jobs.example/start", client=client)

    too_large = httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"content-type": "text/html"}, content=b"12345")
    )
    with httpx.Client(transport=too_large) as client:
        with pytest.raises(JobDescriptionError, match="too large"):
            public_fetcher(max_response_bytes=4).fetch("https://jobs.example/large", client=client)

    image = httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"content-type": "image/png"}, content=b"png")
    )
    with httpx.Client(transport=image) as client:
        with pytest.raises(JobDescriptionError, match="readable job page"):
            public_fetcher().fetch("https://jobs.example/logo", client=client)


def test_job_fetcher_gives_recovery_for_http_and_empty_pages() -> None:
    not_found = httpx.MockTransport(lambda _: httpx.Response(404, headers={"content-type": "text/html"}))
    with httpx.Client(transport=not_found) as client:
        with pytest.raises(JobDescriptionError, match="paste the description"):
            public_fetcher().fetch("https://jobs.example/missing", client=client)

    empty = httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"content-type": "text/html"}, text="<nav>Only nav</nav>")
    )
    with httpx.Client(transport=empty) as client:
        with pytest.raises(JobDescriptionError, match="Paste it manually"):
            public_fetcher().fetch("https://jobs.example/empty", client=client)
