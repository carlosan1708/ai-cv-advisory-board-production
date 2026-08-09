import json
import os

from playwright.sync_api import ConsoleMessage, Page, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")


def test_home_is_product_first_and_opens_workspace(page: Page) -> None:
    page.goto(BASE_URL)
    heading = page.get_by_role(
        "heading", name="Your CV should make its case before you enter the interview."
    )
    expect(heading).to_be_visible()
    expect(page.get_by_text("Technical Recruiter").first).to_be_visible()
    expect(page.get_by_text("Hiring Manager").first).to_be_visible()
    expect(page.get_by_text("Technical Reviewer").first).to_be_visible()
    assert page.locator('link[rel="stylesheet"]').get_attribute("href") == "/static/app.css?v=5"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(247, 248, 250)"
    assert "Georgia" not in page.evaluate("getComputedStyle(document.body).fontFamily")
    page.get_by_test_id("get-started-button").click()
    expect(page).to_have_url(f"{BASE_URL}/workspace")
    expect(page.get_by_role("heading", name="Build a defensible case for this role.")).to_be_visible()


def test_synthetic_demo_renders_complete_findings(page: Page) -> None:
    page.goto(BASE_URL)
    page.get_by_test_id("demo-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    expect(page.get_by_test_id("score")).not_to_have_text("0")
    expect(page.get_by_test_id("score-disclaimer")).to_contain_text("commercial ATS")
    expect(page.get_by_role("heading", name="How the board reached the finding")).to_be_visible()
    expect(page.get_by_role("heading", name="Requirement by requirement")).to_be_visible()
    expect(page.get_by_test_id("evidence-gaps")).to_contain_text("truthful")


def test_custom_review_preserves_input_and_maps_gaps(page: Page) -> None:
    page.goto(f"{BASE_URL}/workspace")
    cv_text = "EXPERIENCE\nBuilt Python services\nSKILLS\nPython\nEDUCATION\nComputer Science"
    page.get_by_test_id("cv-input").fill(cv_text)
    expect(page.locator('[data-char-count="cv-text"]')).to_have_text(str(len(cv_text)))
    page.get_by_role("button", name="Continue to target", exact=True).click()
    expect(page.get_by_role("heading", name="Define the decision your CV must support.")).to_be_visible()
    page.get_by_test_id("job-input").fill("Python Kubernetes Terraform")
    expect(page.locator('[data-char-count="job-text"]')).to_have_text("27")
    page.get_by_role("button", name="← Back to evidence").click()
    expect(page.get_by_test_id("cv-input")).to_have_value(cv_text)
    page.get_by_role("button", name="Continue to target", exact=True).click()
    page.get_by_test_id("analyze-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    expect(page.get_by_test_id("evidence-gaps")).to_contain_text("kubernetes")
    expect(page.get_by_test_id("json-result")).to_contain_text('"schema_version": "1.0"')


def test_guided_review_does_not_advance_without_cv(page: Page) -> None:
    page.goto(f"{BASE_URL}/workspace")
    page.get_by_role("button", name="Continue to target", exact=True).click()
    expect(page.get_by_role("heading", name="Add the evidence you want challenged.")).to_be_visible()
    expect(page.get_by_role("heading", name="Define the decision your CV must support.")).not_to_be_visible()
    expect(page.get_by_test_id("cv-input")).to_be_focused()


def test_structured_assessment_downloads_valid_json(page: Page) -> None:
    page.goto(BASE_URL)
    page.get_by_test_id("demo-button").click()
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


def test_primary_flows_have_clean_browser_console(page: Page) -> None:
    messages: list[str] = []

    def collect_console_message(message: ConsoleMessage) -> None:
        if message.type in {"error", "warning"}:
            messages.append(f"{message.type}: {message.text}")

    page.on("console", collect_console_message)
    page.goto(BASE_URL)
    page.get_by_test_id("get-started-button").click()
    page.get_by_test_id("workspace-demo-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    assert messages == []
