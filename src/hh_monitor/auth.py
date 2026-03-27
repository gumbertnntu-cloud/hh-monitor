from __future__ import annotations

import logging
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LOGIN_SELECTORS = [
    'a[data-qa="login"]',
    'a[href*="/account/login"]',
]


def _has_login_cta(page: object) -> bool:
    for selector in LOGIN_SELECTORS:
        if page.locator(selector).count() > 0:
            return True
    return False


def validate_state(base_url: str, state_path: Path, logger: logging.Logger) -> bool:
    if not state_path.exists():
        logger.info("state file is missing: %s", state_path)
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(state_path))
            page = context.new_page()
            page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector('[data-qa="vacancy-serp__results"]', timeout=45000)
            has_login_cta = _has_login_cta(page)
            cookies = context.cookies("https://hh.ru")
            cookie_names = {cookie.get("name", "") for cookie in cookies}
            has_auth_cookie = "crypted_id" in cookie_names
            is_valid = (not has_login_cta) and has_auth_cookie
            context.close()
            browser.close()
            if is_valid:
                logger.info("state validation passed")
            else:
                logger.warning(
                    "state validation failed: has_login_cta=%s, has_auth_cookie=%s",
                    has_login_cta,
                    has_auth_cookie,
                )
            return is_valid
    except Exception as exc:  # noqa: BLE001
        logger.exception("state validation error: %s", exc)
        return False


def interactive_auth(base_url: str, state_path: Path, logger: logging.Logger) -> bool:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    timeout_sec = 10 * 60
    start = time.monotonic()

    logger.info("starting interactive auth flow")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(base_url, wait_until="domcontentloaded", timeout=60000)

        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout_sec:
                logger.warning("interactive auth timeout")
                context.close()
                browser.close()
                return False
            try:
                page.wait_for_timeout(2000)
                if "account/login" in page.url:
                    continue
                if _has_login_cta(page):
                    continue
                context.storage_state(path=str(state_path))
                state_path.chmod(0o600)
                logger.info("state saved to %s", state_path)
                context.close()
                browser.close()
                return True
            except PlaywrightTimeoutError:
                continue
            except Exception as exc:  # noqa: BLE001
                logger.exception("interactive auth error: %s", exc)
                context.close()
                browser.close()
                return False
