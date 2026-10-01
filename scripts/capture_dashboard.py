"""Capture real dashboard screenshots using an installed headless Chromium browser.

Start the API and Streamlit first. This is developer QA for this local app only.
Usage: python scripts/capture_dashboard.py --browser-path /path/to/chrome
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--browser-path", required=True)
parser.add_argument("--url", default="http://127.0.0.1:8501")
args = parser.parse_args()
destination = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
destination.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.browser_path, headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1)
    page.goto(args.url)
    page.get_by_text("Synthetic contacts", exact=True).wait_for(timeout=30000)
    page.screenshot(path=str(destination / "overview.png"), full_page=True)
    for label, filename in [
        ("Funnel", "funnel"),
        ("Lead Scoring", "scoring"),
        ("Lifecycle Journeys", "journeys"),
        ("AI Recommendations", "recommendations"),
    ]:
        page.get_by_text(label, exact=True).first.click()
        page.locator(".hero h1").filter(has_text=label).wait_for()
        page.locator('[data-testid="stStatusWidget"]').wait_for(state="hidden", timeout=30000)
        if label == "Lead Scoring":
            page.get_by_text("Every point has a reason", exact=True).wait_for()
            page.get_by_role("combobox").first.click()
            page.get_by_text("Demo Northstar 005 · SYN-00005", exact=True).click()
            page.get_by_text("Demo requested: explicit buying intent", exact=False).first.wait_for(
                state="attached"
            )
        if label == "AI Recommendations":
            page.get_by_role("button", name="Run CRM Agent", exact=True).wait_for()
            page.get_by_role("combobox").first.click()
            page.get_by_text("Demo Northstar 005 · SYN-00005", exact=True).click()
            page.get_by_role("button", name="Create unapproved message draft").click()
            page.get_by_text("Let’s plan your requested demo", exact=True).wait_for()
            page.set_viewport_size({"width": 1600, "height": 2100})
        page.screenshot(path=str(destination / f"{filename}.png"), full_page=True)
        print(f"Captured {filename}")
    browser.close()
