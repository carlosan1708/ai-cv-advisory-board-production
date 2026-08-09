import json
import os
from pathlib import Path

from playwright.sync_api import ConsoleMessage, Page, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
CV_TEXT = "EXPERIENCE\nBuilt Python services\nSKILLS\nPython\nEDUCATION\nComputer Science"


def upload_text_cv(page: Page, tmp_path: Path, filename: str = "carlos-resume.txt") -> Path:
    cv_path = tmp_path / filename
    cv_path.write_text(CV_TEXT, encoding="utf-8")
    page.get_by_test_id("cv-file-input").set_input_files(str(cv_path))
    return cv_path


def open_job_step(page: Page, tmp_path: Path) -> None:
    upload_text_cv(page, tmp_path)
    page.get_by_role("button", name="Continue to job").click()


def test_home_is_quiet_document_first_and_opens_workspace(page: Page) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(BASE_URL)
    expect(page.get_by_role("heading", name="Put your CV in front of the board.")).to_be_visible()
    expect(page.get_by_role("heading", name="Upload your CV")).to_be_visible()
    expect(page.get_by_role("heading", name="Add the job link")).to_be_visible()
    expect(page.get_by_role("heading", name="Read the findings")).to_be_visible()
    assert page.locator('link[rel="stylesheet"]').get_attribute("href") == "/static/app.css?v=6"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(247, 247, 244)"
    assert page.evaluate("document.documentElement.scrollHeight <= window.innerHeight + 1") is True
    page.get_by_test_id("get-started-button").click()
    expect(page).to_have_url(f"{BASE_URL}/workspace")
    expect(page.get_by_role("heading", name="Review your CV against a real job.")).to_be_visible()


def test_cv_upload_is_primary_and_text_is_a_collapsed_fallback(page: Page, tmp_path: Path) -> None:
    page.goto(f"{BASE_URL}/workspace")
    expect(page.get_by_test_id("cv-upload-zone")).to_be_visible()
    expect(page.get_by_test_id("cv-input")).not_to_be_visible()
    cv_path = upload_text_cv(page, tmp_path)
    expect(page.get_by_text(cv_path.name, exact=True)).to_be_visible()
    expect(page.locator("[data-file-size]")).to_contain_text("B")
    expect(page.get_by_test_id("cv-upload-zone")).not_to_be_visible()


def test_guided_review_does_not_advance_without_cv(page: Page) -> None:
    page.goto(f"{BASE_URL}/workspace")
    page.get_by_role("button", name="Continue to job").click()
    expect(page.get_by_role("heading", name="Upload the CV you want reviewed.")).to_be_visible()
    expect(page.get_by_role("heading", name="Add the job you are considering.")).not_to_be_visible()
    expect(page.locator("[data-upload-error]")).to_contain_text("Upload a PDF or TXT CV")
    expect(page.get_by_test_id("cv-file-input")).to_be_focused()


def test_invalid_cv_file_has_inline_recovery(page: Page, tmp_path: Path) -> None:
    page.goto(f"{BASE_URL}/workspace")
    bad_file = tmp_path / "resume.docx"
    bad_file.write_text("not a supported CV", encoding="utf-8")
    page.get_by_test_id("cv-file-input").set_input_files(str(bad_file))
    expect(page.locator("[data-upload-error]")).to_have_text("Choose a PDF or TXT CV.")
    expect(page.get_by_test_id("cv-upload-zone")).to_be_visible()


def test_job_url_is_primary_and_manual_description_is_fallback(page: Page, tmp_path: Path) -> None:
    page.goto(f"{BASE_URL}/workspace")
    open_job_step(page, tmp_path)
    expect(page.get_by_test_id("job-url-input")).to_be_visible()
    expect(page.get_by_test_id("job-input")).not_to_be_visible()
    expect(page.get_by_label("Public job link", exact=True)).to_be_visible()
    page.get_by_text("Paste the job description instead", exact=False).click()
    expect(page.get_by_test_id("job-input")).to_be_visible()


def test_job_step_validates_missing_and_non_https_links(page: Page, tmp_path: Path) -> None:
    page.goto(f"{BASE_URL}/workspace")
    open_job_step(page, tmp_path)
    page.get_by_test_id("analyze-button").click()
    expect(page.locator("[data-source-error]")).to_contain_text("Add a public job link")
    page.get_by_test_id("job-url-input").fill("http://jobs.example/role")
    page.get_by_test_id("analyze-button").click()
    expect(page.locator("[data-source-error]")).to_contain_text("complete HTTPS job link")


def test_back_navigation_preserves_selected_cv(page: Page, tmp_path: Path) -> None:
    page.goto(f"{BASE_URL}/workspace")
    cv_path = upload_text_cv(page, tmp_path)
    page.get_by_role("button", name="Continue to job").click()
    page.get_by_role("button", name="Back to CV").click()
    expect(page.get_by_text(cv_path.name, exact=True)).to_be_visible()
    selected_name = page.get_by_test_id("cv-file-input").evaluate("input => input.files[0].name")
    assert selected_name == cv_path.name


def test_uploaded_cv_and_manual_job_complete_review(page: Page, tmp_path: Path) -> None:
    page.goto(f"{BASE_URL}/workspace")
    open_job_step(page, tmp_path)
    page.get_by_text("Paste the job description instead", exact=False).click()
    job_text = "Python Kubernetes Terraform platform leadership"
    page.get_by_test_id("job-input").fill(job_text)
    expect(page.locator('[data-char-count="job-text"]')).to_have_text(str(len(job_text)))
    page.get_by_test_id("analyze-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    expect(page.get_by_test_id("evidence-gaps")).to_contain_text("kubernetes")
    expect(page.get_by_test_id("json-result")).to_contain_text('"schema_version": "1.0"')


def test_pasted_cv_fallback_still_completes_review(page: Page) -> None:
    page.goto(f"{BASE_URL}/workspace")
    page.get_by_text("Paste CV text instead", exact=False).click()
    page.get_by_test_id("cv-input").fill(CV_TEXT)
    expect(page.locator('[data-char-count="cv-text"]')).to_have_text(str(len(CV_TEXT)))
    page.get_by_role("button", name="Continue to job").click()
    page.get_by_text("Paste the job description instead", exact=False).click()
    page.get_by_test_id("job-input").fill("Python backend systems")
    page.get_by_test_id("analyze-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()


def test_synthetic_demo_renders_and_downloads_valid_json(page: Page) -> None:
    page.goto(BASE_URL)
    page.get_by_test_id("demo-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    expect(page.get_by_test_id("score")).not_to_have_text("0")
    expect(page.get_by_test_id("score-disclaimer")).to_contain_text("commercial ATS")
    expect(page.get_by_role("heading", name="How the board reached the finding")).to_be_visible()
    page.get_by_text("Structured assessment").click()
    with page.expect_download() as download_info:
        page.get_by_test_id("download-json-button").click()
    download = download_info.value
    assert download.suggested_filename == "assessment.json"
    payload = json.loads(download.path().read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert 0 <= payload["score"] <= 100


def test_mobile_pages_have_no_horizontal_overflow(page: Page) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL)
    overflow = "document.documentElement.scrollWidth > document.documentElement.clientWidth"
    assert page.evaluate(overflow) is False
    page.goto(f"{BASE_URL}/workspace")
    assert page.evaluate(overflow) is False
    page.get_by_test_id("workspace-demo-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    assert page.evaluate(overflow) is False


def test_primary_flows_have_clean_browser_console(page: Page, tmp_path: Path) -> None:
    messages: list[str] = []

    def collect_console_message(message: ConsoleMessage) -> None:
        if message.type in {"error", "warning"}:
            messages.append(f"{message.type}: {message.text}")

    page.on("console", collect_console_message)
    page.goto(BASE_URL)
    page.get_by_test_id("get-started-button").click()
    upload_text_cv(page, tmp_path)
    page.get_by_role("button", name="Continue to job").click()
    page.get_by_text("Paste the job description instead", exact=False).click()
    page.get_by_test_id("job-input").fill("Python services")
    page.get_by_test_id("analyze-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    assert messages == []
