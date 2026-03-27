from __future__ import annotations

from hh_monitor import browser_support
from hh_monitor.auth import validate_state


def test_validate_state_returns_false_without_state_file(tmp_path) -> None:
    assert (
        validate_state(
            "https://hh.ru/search/vacancy",
            tmp_path / "missing.json",
            logger=_StubLogger(),
        )
        is False
    )


def test_browser_support_exports_consistent_availability_contract() -> None:
    if browser_support.browser_automation_available():
        assert browser_support.browser_automation_reason() == ""
    else:
        assert "Playwright is not available" in browser_support.browser_automation_reason()


class _StubLogger:
    def info(self, *args, **kwargs) -> None:
        return None

    def warning(self, *args, **kwargs) -> None:
        return None

    def exception(self, *args, **kwargs) -> None:
        return None
