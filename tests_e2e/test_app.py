import os

from playwright.sync_api import Page, expect

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")


def test_home_and_synthetic_demo(page: Page) -> None:
    page.goto(BASE_URL)
    expect(page.get_by_role("heading", name="Know what your CV proves.")).to_be_visible()
    page.get_by_test_id("demo-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    expect(page.get_by_test_id("score")).not_to_have_text("0")
    expect(page.get_by_test_id("score-disclaimer")).to_contain_text("commercial ATS")


def test_custom_assessment(page: Page) -> None:
    page.goto(BASE_URL)
    page.get_by_test_id("cv-input").fill("EXPERIENCE\nBuilt Python services\nSKILLS\nPython\nEDUCATION\nCS")
    page.get_by_test_id("job-input").fill("Python Kubernetes Terraform")
    page.get_by_test_id("analyze-button").click()
    expect(page.get_by_test_id("results")).to_be_visible()
    expect(page.get_by_test_id("evidence-gaps")).to_contain_text("kubernetes")
    expect(page.get_by_test_id("json-result")).to_contain_text('"schema_version": "1.0"')


def test_mobile_layout_has_no_horizontal_overflow(page: Page) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL)
    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
    assert overflow is False
