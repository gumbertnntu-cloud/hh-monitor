from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .export_xlsx import export_changes_xlsx
from .logging_conf import configure_logging
from .report import render_console_table
from .runner import SessionInvalidError, run_pipeline
from .settings import AppSettings, load_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Internal service run for hh-monitor.")
    parser.add_argument(
        "--settings",
        default="config/settings.json",
        help="Path to settings JSON file.",
    )
    parser.add_argument("--mode", choices=["fast", "deep"], default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--max-age-days", type=int, default=None)
    parser.add_argument("--export", action="store_true", default=False)
    return parser.parse_args()


def _apply_overrides(settings: AppSettings, args: argparse.Namespace) -> AppSettings:
    if args.mode:
        settings.search.mode = args.mode
    if args.max_pages:
        settings.search.max_pages = args.max_pages
    if args.max_age_days:
        settings.search.max_age_days = args.max_age_days
    return settings


def main() -> int:
    args = parse_args()
    project_root = Path.cwd()
    settings_path = project_root / args.settings

    settings = _apply_overrides(load_settings(settings_path), args)
    settings.ensure_runtime_dirs(project_root)
    logger = configure_logging(project_root / settings.paths.logs_dir)

    try:
        result = run_pipeline(project_root=project_root, settings=settings, logger=logger)
    except SessionInvalidError as exc:
        logger.error("%s", exc)
        print(str(exc))
        return 2
    except Exception as exc:  # noqa: BLE001
        logger.exception("service run failed: %s", exc)
        print(f"service run failed: {exc}")
        return 1

    print(render_console_table(result.rows))
    print(f"run_id={result.run_id} html_report={result.html_report_path}")

    if args.export:
        out_path = (
            project_root
            / settings.paths.exports_dir
            / f"hh_report_run_{result.run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        export_changes_xlsx(result.rows, out_path)
        logger.info("xlsx exported: %s", out_path)
        print(f"xlsx={out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
