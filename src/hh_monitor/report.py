from __future__ import annotations

import html
from pathlib import Path

from tabulate import tabulate

from .models import ChangeRow
from .storage import get_last_run_id, get_run_change_rows


def get_last_run_rows(db_path: Path) -> tuple[int | None, list[ChangeRow]]:
    run_id = get_last_run_id(db_path)
    if run_id is None:
        return None, []
    return run_id, get_run_change_rows(db_path, run_id)


def render_console_table(rows: list[ChangeRow]) -> str:
    if not rows:
        return "No changes in the selected run."
    table = [
        [
            row.date_seen,
            row.vacancy_id,
            row.title,
            row.company,
            row.salary,
            row.area,
            row.url,
            row.match_reason,
            row.status,
        ]
        for row in rows
    ]
    return tabulate(
        table,
        headers=[
            "date_seen",
            "vacancy_id",
            "title",
            "company",
            "salary",
            "area",
            "url",
            "match_reason",
            "status",
        ],
        tablefmt="github",
    )


def generate_html_report(
    rows: list[ChangeRow],
    output_path: Path,
    run_id: int | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    title = f"hh-monitor report (run {run_id})" if run_id is not None else "hh-monitor report"

    body_rows = "\n".join(
        """
        <tr data-status="{status}">
          <td>{date_seen}</td>
          <td>{vacancy_id}</td>
          <td>{title}</td>
          <td>{company}</td>
          <td>{salary}</td>
          <td>{area}</td>
          <td><a href="{url}" target="_blank" rel="noopener">open</a></td>
          <td>{match_reason}</td>
          <td>{status}</td>
        </tr>
        """.format(
            date_seen=html.escape(row.date_seen),
            vacancy_id=html.escape(row.vacancy_id),
            title=html.escape(row.title),
            company=html.escape(row.company),
            salary=html.escape(row.salary),
            area=html.escape(row.area),
            url=html.escape(row.url),
            match_reason=html.escape(row.match_reason),
            status=html.escape(row.status),
        )
        for row in rows
    )

    html_doc = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 20px; }}
    .controls {{ display: flex; gap: 12px; margin-bottom: 12px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f6f6; cursor: pointer; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    .status-new {{ color: #0b7a0b; font-weight: 600; }}
    .status-updated {{ color: #aa6a00; font-weight: 600; }}
    .status-removed {{ color: #b00020; font-weight: 600; }}
  </style>
</head>
<body>
  <h2>{html.escape(title)}</h2>
  <div class="controls">
    <label>Status:
      <select id="statusFilter">
        <option value="">all</option>
        <option value="new">new</option>
        <option value="updated">updated</option>
        <option value="removed">removed</option>
      </select>
    </label>
    <label>Search:
      <input id="searchInput" type="text" placeholder="keyword" />
    </label>
  </div>
  <table id="reportTable">
    <thead>
      <tr>
        <th onclick="sortTable(0)">date_seen</th>
        <th onclick="sortTable(1)">vacancy_id</th>
        <th onclick="sortTable(2)">title</th>
        <th onclick="sortTable(3)">company</th>
        <th onclick="sortTable(4)">salary</th>
        <th onclick="sortTable(5)">area</th>
        <th>url</th>
        <th onclick="sortTable(7)">match_reason</th>
        <th onclick="sortTable(8)">status</th>
      </tr>
    </thead>
    <tbody>
      {body_rows}
    </tbody>
  </table>
<script>
function applyFilter() {{
  const status = document.getElementById('statusFilter').value.toLowerCase();
  const term = document.getElementById('searchInput').value.toLowerCase();
  const rows = Array.from(document.querySelectorAll('#reportTable tbody tr'));
  rows.forEach((row) => {{
    const rowStatus = row.getAttribute('data-status').toLowerCase();
    const text = row.textContent.toLowerCase();
    const passStatus = !status || rowStatus === status;
    const passSearch = !term || text.includes(term);
    row.style.display = passStatus && passSearch ? '' : 'none';
    row.classList.remove('status-new', 'status-updated', 'status-removed');
    row.classList.add('status-' + rowStatus);
  }});
}}
function sortTable(columnIndex) {{
  const tbody = document.querySelector('#reportTable tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const asc = tbody.getAttribute('data-sort-dir') !== 'asc';
  rows.sort((a, b) => {{
    const left = a.children[columnIndex].innerText.trim().toLowerCase();
    const right = b.children[columnIndex].innerText.trim().toLowerCase();
    return asc ? left.localeCompare(right) : right.localeCompare(left);
  }});
  rows.forEach((row) => tbody.appendChild(row));
  tbody.setAttribute('data-sort-dir', asc ? 'asc' : 'desc');
}}
document.getElementById('statusFilter').addEventListener('change', applyFilter);
document.getElementById('searchInput').addEventListener('input', applyFilter);
applyFilter();
</script>
</body>
</html>
"""
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path
