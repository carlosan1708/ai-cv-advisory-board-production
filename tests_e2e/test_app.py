import os

from playwright.sync_api import Page, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")


def test_home_and_synthetic_demo(page: Page) -> None:
    page.goto(BASE_URL)
    heading = page.get_by_role("heading", name="Bring a stronger case to your next opportunity.")
    expect(heading).to_be_visible()
    assert page.locator('link[rel="stylesheet"]').get_attribute("href") == "/static/app.css"
    assert page.evaluate("getComputedStyle(document.body).fontFamily") != '"Times New Roman"'
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(251, 250, 248)"
    page.get_by_test_id("demo-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    expect(page.get_by_test_id("score")).not_to_have_text("0")
    expect(page.get_by_test_id("score-disclaimer")).to_contain_text("commercial ATS")


def test_custom_assessment(page: Page) -> None:
    page.goto(f"{BASE_URL}/workspace")
    page.get_by_test_id("cv-input").fill("EXPERIENCE\nBuilt Python services\nSKILLS\nPython\nEDUCATION\nCS")
    page.get_by_role("button", name="Continue to target role →").click()
    expect(page.get_by_role("heading", name="What role are you targeting?")).to_be_visible()
    page.get_by_test_id("job-input").fill("Python Kubernetes Terraform")
    page.get_by_test_id("analyze-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    expect(page.get_by_test_id("evidence-gaps")).to_contain_text("kubernetes")
    expect(page.get_by_test_id("json-result")).to_contain_text('"schema_version": "1.0"')


def test_guided_review_does_not_advance_without_cv(page: Page) -> None:
    page.goto(f"{BASE_URL}/workspace")
    page.get_by_role("button", name="Continue to target role →").click()
    expect(page.get_by_role("heading", name="Start with your CV.")).to_be_visible()
    expect(page.get_by_role("heading", name="What role are you targeting?")).not_to_be_visible()


def test_mobile_layout_has_no_horizontal_overflow(page: Page) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL)
    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
    assert overflow is False
    page.goto(f"{BASE_URL}/workspace")
    workspace_overflow = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth"
    )
    assert workspace_overflow is False
