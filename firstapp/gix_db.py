"""SQLite persistence for GIX Purchasing (canonical module — import as `gix_db`)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "gix_purchasing.db"

COORDINATOR_STATUSES = (
    "Pending",
    "Approved",
    "Ordered",
    "Completed",
    "Needs Revision",
)
ALL_STATUSES = COORDINATOR_STATUSES + ("Received",)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def norm_team(team: str) -> str:
    return team.strip().lower()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_team_budgets (
            project_id INTEGER NOT NULL,
            team_number TEXT NOT NULL,
            budget_limit REAL NOT NULL,
            PRIMARY KEY (project_id, team_number),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );
        """
    )
    cols = [r[1] for r in conn.execute("PRAGMA table_info(rounds)").fetchall()]
    if "project_id" not in cols:
        conn.execute(
            "ALTER TABLE rounds ADD COLUMN project_id INTEGER REFERENCES projects(id)"
        )
    pcols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
    if "team_budget_limit" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN team_budget_limit REAL")
    rcols = [r[1] for r in conn.execute("PRAGMA table_info(requests)").fetchall()]
    if "last_nudged_at" not in rcols:
        conn.execute("ALTER TABLE requests ADD COLUMN last_nudged_at TEXT")
    if "student_issue_report" not in rcols:
        conn.execute("ALTER TABLE requests ADD COLUMN student_issue_report TEXT")
    if "student_issue_reported_at" not in rcols:
        conn.execute("ALTER TABLE requests ADD COLUMN student_issue_reported_at TEXT")


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                deadline TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER NOT NULL,
                team_number TEXT NOT NULL,
                cfo_name TEXT NOT NULL,
                supplier TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL,
                purchase_link TEXT NOT NULL,
                student_notes TEXT,
                instructor_approval TEXT DEFAULT '',
                order_number TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending',
                coordinator_notes TEXT DEFAULT '',
                submitted_at TEXT NOT NULL,
                received_at TEXT,
                last_nudged_at TEXT,
                student_issue_report TEXT,
                student_issue_reported_at TEXT,
                FOREIGN KEY (round_id) REFERENCES rounds(id)
            );

            CREATE INDEX IF NOT EXISTS idx_requests_round ON requests(round_id);
            """
        )
        _migrate(conn)


def add_project(name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, created_at) VALUES (?, ?)",
            (name.strip(), utc_now_iso()),
        )
        return int(cur.lastrowid)


def list_projects() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, team_budget_limit FROM projects ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_project(project_id: int) -> None:
    """Remove project, unlink all rounds, and delete team budget rows for this project."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE rounds SET project_id = NULL WHERE project_id = ?", (project_id,)
        )
        conn.execute(
            "DELETE FROM project_team_budgets WHERE project_id = ?", (project_id,)
        )
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def set_project_team_budget(project_id: int, team_budget_limit: float) -> None:
    """Same per-team budget for every team in this project."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET team_budget_limit = ? WHERE id = ?",
            (float(team_budget_limit), project_id),
        )


def get_project_team_budget_limit(project_id: int) -> float | None:
    """Per-team budget cap for the project (identical for all teams). Legacy per-team rows used if unset."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT team_budget_limit FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    if row and row["team_budget_limit"] is not None:
        return float(row["team_budget_limit"])
    with get_conn() as conn:
        legacy = conn.execute(
            """
            SELECT budget_limit FROM project_team_budgets
            WHERE project_id = ? LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    return float(legacy["budget_limit"]) if legacy else None


def set_round_project(round_id: int, project_id: int | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE rounds SET project_id = ? WHERE id = ?",
            (project_id, round_id),
        )


def add_round(name: str, deadline_iso: str, project_id: int | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO rounds (name, deadline, created_at, project_id) VALUES (?, ?, ?, ?)",
            (name.strip(), deadline_iso, utc_now_iso(), project_id),
        )
        return int(cur.lastrowid)


def list_rounds() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.name, r.deadline, r.created_at, r.project_id,
                   p.name AS project_name
            FROM rounds r
            LEFT JOIN projects p ON r.project_id = p.id
            ORDER BY r.id DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def round_is_open(deadline_iso: str) -> bool:
    """Compare naive deadlines with local time; aware ISO strings use their timezone."""
    try:
        dl = datetime.fromisoformat(deadline_iso.replace("Z", "+00:00"))
        if dl.tzinfo is None:
            return datetime.now() <= dl
        return datetime.now(dl.tzinfo) <= dl
    except (ValueError, TypeError):
        return False


def add_request(
    round_id: int,
    team_number: str,
    cfo_name: str,
    supplier: str,
    item_name: str,
    quantity: float,
    unit_price: float,
    purchase_link: str,
    student_notes: str | None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO requests (
                round_id, team_number, cfo_name, supplier, item_name,
                quantity, unit_price, purchase_link, student_notes,
                status, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
            """,
            (
                round_id,
                team_number.strip(),
                cfo_name.strip(),
                supplier,
                item_name.strip(),
                quantity,
                unit_price,
                purchase_link.strip(),
                (student_notes or "").strip() or None,
                utc_now_iso(),
            ),
        )
        return int(cur.lastrowid)


def list_requests(round_id: int | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if round_id is None:
            rows = conn.execute(
                """
                SELECT r.*, rd.name AS round_name, rd.deadline AS round_deadline,
                       rd.project_id, p.name AS project_name
                FROM requests r
                JOIN rounds rd ON r.round_id = rd.id
                LEFT JOIN projects p ON rd.project_id = p.id
                ORDER BY r.submitted_at DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT r.*, rd.name AS round_name, rd.deadline AS round_deadline,
                       rd.project_id, p.name AS project_name
                FROM requests r
                JOIN rounds rd ON r.round_id = rd.id
                LEFT JOIN projects p ON rd.project_id = p.id
                WHERE r.round_id = ?
                ORDER BY r.submitted_at DESC
                """,
                (round_id,),
            ).fetchall()
    return [dict(x) for x in rows]


def count_requests_for_round(round_id: int) -> int:
    """Return the total number of requests submitted for ``round_id``."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE round_id = ?",
            (round_id,),
        ).fetchone()
    return int(row["n"]) if row else 0


def get_requests_for_student(team_number: str, cfo_name: str) -> list[dict[str, Any]]:
    t = team_number.strip().lower()
    c = cfo_name.strip().lower()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.*, rd.name AS round_name, rd.deadline AS round_deadline,
                   rd.project_id, p.name AS project_name
            FROM requests r
            JOIN rounds rd ON r.round_id = rd.id
            LEFT JOIN projects p ON rd.project_id = p.id
            WHERE lower(trim(r.team_number)) = ? AND lower(trim(r.cfo_name)) = ?
            ORDER BY r.submitted_at DESC
            """,
            (t, c),
        ).fetchall()
    return [dict(x) for x in rows]


def update_request_coordinator(
    request_id: int,
    order_number: str,
    status: str,
    instructor_approval: str,
    coordinator_notes: str,
    student_issue_report: str | None = None,
) -> None:
    """Coordinator updates request; empty student_issue_report clears the student report and timestamp."""
    msg = (student_issue_report or "").strip()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT received_at, student_issue_report, student_issue_reported_at
            FROM requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()
        if not row:
            return
        prev_received = row["received_at"]
        if status == "Received":
            received_at = prev_received or utc_now_iso()
        else:
            received_at = None
        if not msg:
            sir, siat = None, None
        else:
            sir = msg
            prev_msg = (row["student_issue_report"] or "").strip()
            prev_at = row["student_issue_reported_at"]
            if prev_msg == msg:
                siat = prev_at
            else:
                siat = prev_at or utc_now_iso()

        conn.execute(
            """
            UPDATE requests SET
                order_number = ?,
                status = ?,
                instructor_approval = ?,
                coordinator_notes = ?,
                received_at = ?,
                student_issue_report = ?,
                student_issue_reported_at = ?
            WHERE id = ?
            """,
            (
                order_number.strip(),
                status,
                instructor_approval.strip(),
                coordinator_notes.strip(),
                received_at,
                sir,
                siat,
                request_id,
            ),
        )


def report_student_issue(
    request_id: int, team_number: str, cfo_name: str, message: str
) -> tuple[bool, str]:
    """Attach or replace a problem report on a request (must match team + CFO)."""
    msg = (message or "").strip()
    if not msg:
        return False, "Please describe the problem."
    t = norm_team(team_number)
    c = norm_team(cfo_name)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id FROM requests
            WHERE id = ? AND lower(trim(team_number)) = ? AND lower(trim(cfo_name)) = ?
            """,
            (request_id, t, c),
        ).fetchone()
        if not row:
            return False, "Request not found or does not match your team and CFO."
        conn.execute(
            """
            UPDATE requests SET student_issue_report = ?, student_issue_reported_at = ?
            WHERE id = ?
            """,
            (msg, utc_now_iso(), request_id),
        )
    return True, ""


def mark_received_by_student(request_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE requests SET status = 'Received', received_at = ?
            WHERE id = ? AND status IN ('Ordered', 'Completed')
            """,
            (utc_now_iso(), request_id),
        )


def _parse_nudge_time(last_nudged_at: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(last_nudged_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def seconds_until_next_nudge(last_nudged_at: str | None) -> int:
    """Seconds until another nudge is allowed; 0 if none recorded or cooldown has passed."""
    if not last_nudged_at:
        return 0
    prev = _parse_nudge_time(last_nudged_at)
    if prev is None:
        return 0
    elapsed = (datetime.now(timezone.utc) - prev).total_seconds()
    remaining = timedelta(hours=24).total_seconds() - elapsed
    return max(0, int(remaining))


def record_student_nudge(request_id: int, team_number: str, cfo_name: str) -> tuple[bool, str]:
    """Verify student identity and status; enforce 24h cooldown per request."""
    t = norm_team(team_number)
    c = cfo_name.strip().lower()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, status, team_number, cfo_name, last_nudged_at
            FROM requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()
    if not row:
        return (False, "Request not found.")
    if norm_team(row["team_number"]) != t or str(row["cfo_name"]).strip().lower() != c:
        return (False, "That request does not match your team and CFO.")
    if row["status"] not in ("Pending", "Approved"):
        return (False, "You can only nudge requests that are pending or approved.")
    rem = seconds_until_next_nudge(row["last_nudged_at"])
    if rem > 0:
        h, m = rem // 3600, (rem % 3600) // 60
        return (False, f"You can send another nudge in {h}h {m}m.")
    with get_conn() as conn:
        conn.execute(
            "UPDATE requests SET last_nudged_at = ? WHERE id = ?",
            (utc_now_iso(), request_id),
        )
    return (True, "")


def get_round_project_id(round_id: int) -> int | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT project_id FROM rounds WHERE id = ?", (round_id,)
        ).fetchone()
    if not row:
        return None
    pid = row["project_id"]
    return int(pid) if pid is not None else None


def get_project_round_ids(project_id: int) -> list[int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM rounds WHERE project_id = ?", (project_id,)
        ).fetchall()
    return [int(r["id"]) for r in rows]


def project_team_finance_rows(project_id: int) -> list[dict[str, Any]]:
    """Per-team budget, requested (all lines), spent (Ordered/Completed), remaining."""
    with get_conn() as conn:
        proj = conn.execute(
            "SELECT name FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    project_name = proj["name"] if proj else ""

    team_cap = get_project_team_budget_limit(project_id)
    has_budget = team_cap is not None
    budget_val = float(team_cap) if team_cap is not None else 0.0

    round_ids = get_project_round_ids(project_id)

    if not round_ids:
        return []

    placeholders = ",".join("?" * len(round_ids))
    with get_conn() as conn:
        req_rows = conn.execute(
            f"""
            SELECT lower(trim(team_number)) AS tn, MIN(team_number) AS display_team,
                   SUM(quantity * unit_price) AS total_requested
            FROM requests
            WHERE round_id IN ({placeholders})
            GROUP BY lower(trim(team_number))
            """,
            round_ids,
        ).fetchall()

        spent_rows = conn.execute(
            f"""
            SELECT lower(trim(team_number)) AS tn,
                   SUM(quantity * unit_price) AS total_spent
            FROM requests
            WHERE round_id IN ({placeholders})
              AND status IN ('Ordered', 'Completed')
            GROUP BY lower(trim(team_number))
            """,
            round_ids,
        ).fetchall()

    requested_map = {r["tn"]: float(r["total_requested"] or 0) for r in req_rows}
    display_team_map = {r["tn"]: r["display_team"] for r in req_rows}
    spent_map = {r["tn"]: float(r["total_spent"] or 0) for r in spent_rows}

    team_keys: set[str] = set(requested_map.keys()) | set(spent_map.keys())

    out = []
    for tk in sorted(team_keys, key=lambda k: display_team_map.get(k, k).lower()):
        display = display_team_map[tk]
        tot_req = requested_map.get(tk, 0.0)
        tot_spent = spent_map.get(tk, 0.0)
        remaining = budget_val - tot_req
        over = tot_req > budget_val
        out.append(
            {
                "team_number": display,
                "budget_limit": budget_val,
                "budget_configured": has_budget,
                "total_requested": tot_req,
                "total_spent": tot_spent,
                "remaining": remaining,
                "over_budget": over,
                "project_name": project_name,
            }
        )

    return out


def get_budget_snapshot_for_team_project(team_number: str, project_id: int) -> dict[str, Any] | None:
    """Student/coordinator snapshot: budget, requested, spent, remaining; None if project missing."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    if not row:
        return None
    project_name = row["name"]
    round_ids = get_project_round_ids(project_id)
    tn = norm_team(team_number)
    budget = get_project_team_budget_limit(project_id)
    has_budget = budget is not None
    if budget is None:
        budget = 0.0

    if not round_ids:
        return {
            "project_id": project_id,
            "project_name": project_name,
            "team_number": team_number.strip(),
            "budget_limit": budget,
            "budget_configured": has_budget,
            "total_requested": 0.0,
            "total_spent": 0.0,
            "remaining": budget,
            "over_budget": False,
            "low_remaining": False,
        }

    placeholders = ",".join("?" * len(round_ids))
    with get_conn() as conn:
        req = conn.execute(
            f"""
            SELECT COALESCE(SUM(quantity * unit_price), 0) AS t
            FROM requests
            WHERE round_id IN ({placeholders}) AND lower(trim(team_number)) = ?
            """,
            (*round_ids, tn),
        ).fetchone()
        sp = conn.execute(
            f"""
            SELECT COALESCE(SUM(quantity * unit_price), 0) AS t
            FROM requests
            WHERE round_id IN ({placeholders})
              AND lower(trim(team_number)) = ?
              AND status IN ('Ordered', 'Completed')
            """,
            (*round_ids, tn),
        ).fetchone()
    tot_req = float(req["t"] or 0)
    tot_spent = float(sp["t"] or 0)
    remaining = budget - tot_req
    over = tot_req > budget
    low = has_budget and budget > 0 and (remaining / budget) < 0.2 and remaining >= 0
    return {
        "project_id": project_id,
        "project_name": project_name,
        "team_number": team_number.strip(),
        "budget_limit": budget,
        "budget_configured": has_budget,
        "total_requested": tot_req,
        "total_spent": tot_spent,
        "remaining": remaining,
        "over_budget": over,
        "low_remaining": low,
    }


def get_budget_snapshot_for_team_round(team_number: str, round_id: int) -> dict[str, Any] | None:
    pid = get_round_project_id(round_id)
    if pid is None:
        return None
    return get_budget_snapshot_for_team_project(team_number, pid)
