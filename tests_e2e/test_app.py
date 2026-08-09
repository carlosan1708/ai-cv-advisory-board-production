import json
import os
from pathlib import Path
from uuid import uuid4

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


def test_home_presents_free_and_private_modes(page: Page) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(BASE_URL)
    expect(page.get_by_role("heading", name="Choose what you need today.")).to_be_visible()
    expect(page.get_by_role("heading", name="Check one CV against one job.")).to_be_visible()
    expect(page.get_by_role("heading", name="Run your full application pipeline.")).to_be_visible()
    expect(page.get_by_text("Shared $5 monthly AI pool", exact=False)).to_be_visible()
    expect(page.get_by_text("no in-app AI usage cap", exact=False)).to_be_visible()
    assert page.locator('link[rel="stylesheet"]').get_attribute("href") == "/static/app.css?v=8"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(244, 243, 239)"
    page.get_by_test_id("member-mode-button").click()
    expect(page).to_have_url(f"{BASE_URL}/dashboard")
    expect(page.get_by_role("heading", name="Your search, at a glance.")).to_be_visible()


def test_cv_library_reviews_and_saves_a_new_version(page: Page, tmp_path: Path) -> None:
    page.goto(f"{BASE_URL}/cvs")
    label = f"Standalone CV {uuid4().hex[:6]}"
    page.get_by_role("button", name="Upload a CV", exact=True).first.click()
    upload_dialog = page.locator("[data-upload-dialog]")
    upload_dialog.get_by_label("Version label").fill(label)
    cv_path = tmp_path / "standalone-cv.txt"
    cv_path.write_text(f"{CV_TEXT}\nDelivered systems for 50 teams", encoding="utf-8")
    upload_dialog.get_by_label("CV file").set_input_files(str(cv_path))
    page.get_by_role("button", name="Add to library").click()
    card = page.locator(".cv-card").filter(has_text=label)
    expect(card).to_be_visible()
    card.get_by_role("button", name="Review CV").click()
    expect(page.locator("[data-review-result]")).to_be_visible()
    expect(page.locator("[data-review-score]")).not_to_have_text("0")
    page.locator("[data-review-dialog]").get_by_role("button", name="Close").last.click()
    card.get_by_role("button", name="Edit as new version").click()
    page.locator("[data-edit-dialog]").get_by_label("New version label").fill(f"{label} revised")
    page.locator("[data-edit-dialog]").get_by_label("CV content").fill(
        f"{CV_TEXT}\nDelivered reliable systems for 100 teams"
    )
    page.get_by_role("button", name="Save new version").click()
    expect(page.get_by_role("heading", name=f"{label} revised")).to_be_visible()
    page.goto(f"{BASE_URL}/dashboard")
    page.get_by_role("button", name="Start an AI expert review").click()
    panel = page.locator("[data-expert-dialog]")
    expect(panel.locator("[data-expert-application-fields]")).to_be_hidden()
    panel.get_by_label("CV version").select_option(label=f"{label} revised")
    panel.get_by_role("button", name="Ask the AI panel").click()
    expect(panel.locator("[data-expert-result]")).to_be_visible()
    expect(panel.get_by_role("heading", name="Recruiter")).to_be_visible()
    expect(panel.get_by_role("heading", name="Hiring Manager")).to_be_visible()
    expect(panel.get_by_role("heading", name="Technical Reviewer")).to_be_visible()


def test_tracker_add_move_filter_and_funnel_update(page: Page) -> None:
    page.goto(f"{BASE_URL}/tracker")
    role = f"Staff AI Engineer {uuid4().hex[:6]}"
    applied_before = int(page.locator('[data-count="applied"]').text_content())
    interviewing_before = int(page.locator('[data-count="interviewing"]').text_content())
    page.get_by_role("button", name="Add application", exact=True).first.click()
    page.get_by_label("Company").fill("Acme")
    page.get_by_label("Role").fill(role)
    page.get_by_label("Status").select_option("applied")
    page.get_by_role("button", name="Add application", exact=True).last.click()
    expect(page.get_by_role("heading", name=role)).to_be_visible()
    expect(page.locator('[data-count="applied"]')).to_have_text(str(applied_before + 1))
    page.get_by_label(f"Move {role} at Acme").select_option("interviewing")
    expect(page.locator('[data-count="applied"]')).to_have_text(str(applied_before))
    expect(page.locator('[data-count="interviewing"]')).to_have_text(str(interviewing_before + 1))
    page.locator('[data-filter="interviewing"]').click()
    expect(page.get_by_role("heading", name=role)).to_be_visible()


def test_tracker_uploads_and_attaches_exact_cv_version(page: Page, tmp_path: Path) -> None:
    page.goto(f"{BASE_URL}/cvs")
    version_label = f"AI platform · {uuid4().hex[:6]}"
    page.get_by_role("button", name="Upload a CV", exact=True).first.click()
    upload_dialog = page.locator("[data-upload-dialog]")
    upload_dialog.get_by_label("Version label").fill(version_label)
    cv_path = tmp_path / "platform-cv.txt"
    cv_path.write_text(CV_TEXT, encoding="utf-8")
    upload_dialog.get_by_label("CV file").set_input_files(str(cv_path))
    page.get_by_role("button", name="Add to library").click()
    expect(page.get_by_role("heading", name=version_label)).to_be_visible()
    page.goto(f"{BASE_URL}/tracker")
    page.get_by_role("button", name="Add application", exact=True).first.click()
    page.get_by_label("Company").fill("Northstar")
    page.get_by_label("Role").fill(f"ML Platform Lead {uuid4().hex[:6]}")
    page.locator("[data-application-dialog]").get_by_label("CV version").select_option(
        label=version_label
    )
    page.get_by_role("button", name="Add application", exact=True).last.click()
    expect(page.get_by_text(f"CV · {version_label}")).to_be_visible()


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
    page.goto(f"{BASE_URL}/workspace")
    page.get_by_test_id("workspace-demo-button").click()
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
    page.goto(f"{BASE_URL}/tracker")
    assert page.evaluate(overflow) is False


def test_primary_flows_have_clean_browser_console(page: Page, tmp_path: Path) -> None:
    messages: list[str] = []

    def collect_console_message(message: ConsoleMessage) -> None:
        if message.type in {"error", "warning"}:
            messages.append(f"{message.type}: {message.text}")

    page.on("console", collect_console_message)
    page.goto(BASE_URL)
    page.get_by_test_id("free-mode-button").click()
    upload_text_cv(page, tmp_path)
    page.get_by_role("button", name="Continue to job").click()
    page.get_by_text("Paste the job description instead", exact=False).click()
    page.get_by_test_id("job-input").fill("Python services")
    page.get_by_test_id("analyze-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    assert messages == []
