from __future__ import annotations

from typing import Any


class BrowserAutomationUnavailableError(RuntimeError):
    pass


_IMPORT_ERROR: Exception | None = None

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright as _sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception as exc:  # noqa: BLE001
    PLAYWRIGHT_AVAILABLE = False
    _IMPORT_ERROR = exc

    class PlaywrightError(Exception):
        pass

    class PlaywrightTimeoutError(Exception):
        pass

    _sync_playwright = None


def browser_automation_available() -> bool:
    return PLAYWRIGHT_AVAILABLE


def browser_automation_reason() -> str:
    if PLAYWRIGHT_AVAILABLE:
        return ""
    if _IMPORT_ERROR is None:
        return "Playwright is not available in this build."
    return f"Playwright is not available in this build: {_IMPORT_ERROR}"


def require_browser_automation() -> None:
    if PLAYWRIGHT_AVAILABLE:
        return
    raise BrowserAutomationUnavailableError(browser_automation_reason())


def sync_playwright() -> Any:
    require_browser_automation()
    assert _sync_playwright is not None
    return _sync_playwright()
