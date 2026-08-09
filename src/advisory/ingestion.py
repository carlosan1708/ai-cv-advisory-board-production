from __future__ import annotations

import io
import ipaddress
import json
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from pypdf import PdfReader


class CvDocumentError(ValueError):
    pass


class JobDescriptionError(ValueError):
    pass


@dataclass(frozen=True)
class CvDocumentParser:
    max_file_bytes: int = 5 * 1024 * 1024
    max_chars: int = 30_000
    max_pdf_pages: int = 40

    def parse(self, filename: str, content: bytes) -> str:
        if not content:
            raise CvDocumentError("The selected file is empty. Choose a PDF or TXT CV.")
        if len(content) > self.max_file_bytes:
            raise CvDocumentError("The CV is larger than 5 MB. Choose a smaller PDF or TXT file.")

        suffix = Path(filename).suffix.lower()
        if suffix == ".txt":
            text = self._parse_text(content)
        elif suffix == ".pdf":
            text = self._parse_pdf(content)
        else:
            raise CvDocumentError("That file type is not supported. Choose a PDF or TXT CV.")

        text = text.replace("\x00", "").replace("\r\n", "\n").strip()
        if not text:
            raise CvDocumentError(
                "No readable text was found. If this is a scanned PDF, paste the CV text instead."
            )
        if len(text) > self.max_chars:
            raise CvDocumentError(
                f"The extracted CV is longer than {self.max_chars:,} characters. Use a shorter version."
            )
        return text

    @staticmethod
    def _parse_text(content: bytes) -> str:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CvDocumentError(
                "The TXT file must use UTF-8 encoding. Save it as UTF-8 and try again."
            ) from exc

    def _parse_pdf(self, content: bytes) -> str:
        if not content.startswith(b"%PDF-"):
            raise CvDocumentError("The selected file is not a valid PDF.")
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted and reader.decrypt("") == 0:
                raise CvDocumentError("Password-protected PDFs are not supported. Upload an unlocked copy.")
            if len(reader.pages) > self.max_pdf_pages:
                raise CvDocumentError(
                    f"The PDF has more than {self.max_pdf_pages} pages. Upload a shorter CV."
                )
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except CvDocumentError:
            raise
        except Exception as exc:
            raise CvDocumentError(
                "The PDF could not be read. Upload a valid PDF or paste the CV text."
            ) from exc


Resolver = Callable[[str], Sequence[str]]


def resolve_hostname(hostname: str) -> Sequence[str]:
    addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    return sorted({str(address[4][0]) for address in addresses})


def _clean_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            self.skip_depth += 1
        elif tag in {"br", "p", "div", "li", "section", "article", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif tag in {"p", "div", "li", "section", "article", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return _clean_text("".join(self.parts))


class _JobPageParser(HTMLParser):
    preferred_markers = {
        "description__text",
        "show-more-less-html__markup",
        "jobdescriptiontext",
        "job-description",
        "job_description",
        "posting-description",
    }
    void_tags = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.preferred_depth = 0
        self.preferred_parts: list[str] = []
        self.preferred_candidates: list[str] = []
        self.fallback_depth = 0
        self.fallback_parts: list[str] = []
        self.fallback_candidates: list[str] = []
        self.skip_depth = 0
        self.json_ld_depth = 0
        self.json_ld_parts: list[str] = []
        self.json_ld_blocks: list[str] = []

    @staticmethod
    def _is_preferred(tag: str, attrs: dict[str, str]) -> bool:
        marker_text = " ".join((attrs.get("id", ""), attrs.get("class", ""))).lower()
        return attrs.get("itemprop", "").lower() == "description" or any(
            marker in marker_text for marker in _JobPageParser.preferred_markers
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
            self.json_ld_depth = 1
            self.json_ld_parts = []
            return
        if self.json_ld_depth:
            self.json_ld_depth += 1
            return

        if tag in {"script", "style", "svg", "noscript", "nav", "header", "footer"}:
            self.skip_depth += 1

        if self.preferred_depth and tag not in self.void_tags:
            self.preferred_depth += 1
        elif self._is_preferred(tag, attributes):
            self.preferred_depth = 1
            self.preferred_parts = []

        if self.fallback_depth and tag not in self.void_tags:
            self.fallback_depth += 1
        elif tag in {"main", "article"}:
            self.fallback_depth = 1
            self.fallback_parts = []

        if tag in {"br", "p", "div", "li", "section", "h1", "h2", "h3"}:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.json_ld_depth:
            self.json_ld_depth -= 1
            if not self.json_ld_depth:
                self.json_ld_blocks.append("".join(self.json_ld_parts))
            return

        if tag in {"script", "style", "svg", "noscript", "nav", "header", "footer"} and self.skip_depth:
            self.skip_depth -= 1

        if tag in {"p", "div", "li", "section", "h1", "h2", "h3"}:
            self._append("\n")

        if self.preferred_depth:
            self.preferred_depth -= 1
            if not self.preferred_depth:
                self.preferred_candidates.append(_clean_text("".join(self.preferred_parts)))
        if self.fallback_depth:
            self.fallback_depth -= 1
            if not self.fallback_depth:
                self.fallback_candidates.append(_clean_text("".join(self.fallback_parts)))

    def handle_data(self, data: str) -> None:
        if self.json_ld_depth:
            self.json_ld_parts.append(data)
        elif not self.skip_depth:
            self._append(data)

    def _append(self, value: str) -> None:
        if self.preferred_depth:
            self.preferred_parts.append(value)
        if self.fallback_depth:
            self.fallback_parts.append(value)


def _find_job_posting_description(value: Any) -> str:
    if isinstance(value, dict):
        item_type = value.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        description = value.get("description")
        if "JobPosting" in types and isinstance(description, str):
            return description
        for nested in value.values():
            result = _find_job_posting_description(nested)
            if result:
                return result
    elif isinstance(value, list):
        for nested in value:
            result = _find_job_posting_description(nested)
            if result:
                return result
    return ""


def extract_job_description(document: str) -> str:
    parser = _JobPageParser()
    parser.feed(document)

    for block in parser.json_ld_blocks:
        try:
            description = _find_job_posting_description(json.loads(block))
        except json.JSONDecodeError:
            continue
        if description:
            text_parser = _PlainTextParser()
            text_parser.feed(description)
            extracted = text_parser.text()
            if extracted:
                return extracted

    candidates = [candidate for candidate in parser.preferred_candidates if candidate]
    if not candidates:
        candidates = [candidate for candidate in parser.fallback_candidates if candidate]
    return max(candidates, key=len) if candidates else ""


@dataclass(frozen=True)
class JobDescriptionFetcher:
    resolver: Resolver = resolve_hostname
    max_response_bytes: int = 1_000_000
    max_chars: int = 30_000
    max_redirects: int = 3
    timeout_seconds: float = 8.0

    def _validated_url(self, raw_url: str) -> tuple[str, frozenset[str]]:
        url = raw_url.strip()
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError as exc:
            raise JobDescriptionError("Enter a valid HTTPS job URL.") from exc

        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise JobDescriptionError("Use a complete HTTPS job URL.")
        if parsed.username or parsed.password or port not in {None, 443}:
            raise JobDescriptionError("The job URL contains unsupported credentials or a custom port.")

        hostname = parsed.hostname.rstrip(".").lower()
        try:
            addresses = self.resolver(hostname)
        except OSError as exc:
            raise JobDescriptionError(
                "The job site could not be found. Check the link or paste the description."
            ) from exc
        if not addresses:
            raise JobDescriptionError(
                "The job site could not be found. Check the link or paste the description."
            )

        try:
            public = all(ipaddress.ip_address(address).is_global for address in addresses)
        except ValueError as exc:
            raise JobDescriptionError("The job URL could not be validated.") from exc
        if not public:
            raise JobDescriptionError("Only public job-page URLs are supported.")
        return parsed.geturl(), frozenset(addresses)

    @staticmethod
    def _validate_connected_peer(
        response: httpx.Response,
        allowed_addresses: frozenset[str],
        *,
        required: bool,
    ) -> None:
        stream = response.extensions.get("network_stream")
        if stream is None:
            if required:
                raise JobDescriptionError("The job page connection could not be validated safely.")
            return
        peer = stream.get_extra_info("server_addr")
        if not isinstance(peer, tuple) or not peer:
            raise JobDescriptionError("The job page connection could not be validated safely.")
        connected_address = str(peer[0])
        try:
            is_public = ipaddress.ip_address(connected_address).is_global
        except ValueError as exc:
            raise JobDescriptionError("The job page connection could not be validated safely.") from exc
        if not is_public or connected_address not in allowed_addresses:
            raise JobDescriptionError("The job page resolved to an unexpected network address.")

    def fetch(self, raw_url: str, *, client: httpx.Client | None = None) -> str:
        current_url = raw_url
        owns_client = client is None
        active_client = client or httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "AI-CV-Advisory-Board/1.0 (+public job description reader)"},
        )
        try:
            for redirect_count in range(self.max_redirects + 1):
                current_url, allowed_addresses = self._validated_url(current_url)
                with active_client.stream("GET", current_url) as response:
                    self._validate_connected_peer(response, allowed_addresses, required=owns_client)
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count == self.max_redirects:
                            raise JobDescriptionError("The job page redirected too many times.")
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                        raise JobDescriptionError("That link does not point to a readable job page.")
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > self.max_response_bytes:
                        raise JobDescriptionError("The job page is too large to process safely.")

                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self.max_response_bytes:
                            raise JobDescriptionError("The job page is too large to process safely.")
                    encoding = response.encoding or "utf-8"
                    document = bytes(body).decode(encoding, errors="replace")

                extracted = (
                    _clean_text(document)
                    if content_type == "text/plain"
                    else extract_job_description(document)
                )
                if not extracted:
                    raise JobDescriptionError(
                        "We could not read a job description from that page. Paste it manually instead."
                    )
                if len(extracted) > self.max_chars:
                    raise JobDescriptionError(
                        "The extracted job description is too long. Paste the relevant text."
                    )
                return extracted
        except JobDescriptionError:
            raise
        except (httpx.HTTPError, UnicodeError, ValueError) as exc:
            raise JobDescriptionError(
                "The job page could not be read. Check the link or paste the description instead."
            ) from exc
        finally:
            if owns_client:
                active_client.close()

        raise JobDescriptionError("The job page redirected too many times.")
