"""Data loading and database call functions."""

from __future__ import annotations

import streamlit as st

import gix_db as db

# Export status constants from database module
ALL_STATUSES = db.ALL_STATUSES


def init_db() -> None:
    """Initialize the database."""
    db.init_db()


def load_coordinator_password() -> str:
    """Load coordinator password from secrets or use default.

    Returns:
        Coordinator password string
    """
    try:
        return st.secrets.get("COORDINATOR_PASSWORD", "gix-coordinator")
    except Exception:
        return "gix-coordinator"


def get_all_rounds() -> list[dict]:
    """Get all purchasing rounds.

    Returns:
        List of round dictionaries
    """
    return db.list_rounds()


def get_all_projects() -> list[dict]:
    """Get all projects.

    Returns:
        List of project dictionaries
    """
    return db.list_projects()


def get_all_requests(round_id: int | None = None) -> list[dict]:
    """Get all requests, optionally filtered by round.

    Args:
        round_id: Optional round ID to filter by

    Returns:
        List of request dictionaries
    """
    return db.list_requests(round_id)


def get_requests_by_student(team: str, cfo: str) -> list[dict]:
    """Get requests for a specific student (team and CFO).

    Args:
        team: Team number
        cfo: CFO name

    Returns:
        List of request dictionaries
    """
    return db.get_requests_for_student(team, cfo)


def get_budget_snapshot(team: str, round_id: int) -> dict | None:
    """Get budget snapshot for a team in a round.

    Args:
        team: Team number
        round_id: Round ID

    Returns:
        Budget snapshot dictionary or None if not found
    """
    return db.get_budget_snapshot_for_team_round(team, round_id)


def get_project_team_finance(project_id: int) -> list[dict]:
    """Get finance rows for all teams in a project.

    Args:
        project_id: Project ID

    Returns:
        List of team finance dictionaries
    """
    return db.project_team_finance_rows(project_id)


def get_project_team_budget_limit(project_id: int) -> float | None:
    """Get per-team budget limit for a project.

    Args:
        project_id: Project ID

    Returns:
        Budget limit or None if not set
    """
    return db.get_project_team_budget_limit(project_id)


def check_round_is_open(deadline: str) -> bool:
    """Check if a round is still open (before deadline).

    Args:
        deadline: ISO format deadline string

    Returns:
        True if round is open, False if closed
    """
    return db.round_is_open(deadline)


def get_seconds_until_next_nudge(last_nudged_at: str | None) -> int:
    """Get seconds until next nudge is allowed.

    Args:
        last_nudged_at: ISO format timestamp of last nudge or None

    Returns:
        Seconds remaining (0 if can nudge now, negative if unrestricted)
    """
    return db.seconds_until_next_nudge(last_nudged_at)


def submit_purchase_request(
    round_id: int,
    team: str,
    cfo: str,
    supplier: str,
    item: str,
    qty: float,
    unit_price: float,
    link: str,
    notes: str,
) -> None:
    """Submit a new purchase request.

    Args:
        round_id: Round ID
        team: Team number
        cfo: CFO name
        supplier: Supplier name
        item: Item name
        qty: Quantity
        unit_price: Unit price in USD
        link: Purchase link
        notes: Optional notes
    """
    db.add_request(round_id, team, cfo, supplier, item, qty, unit_price, link, notes)


def report_student_issue(request_id: int, team: str, cfo: str, description: str) -> tuple[bool, str]:
    """Report an issue with a request.

    Args:
        request_id: Request ID
        team: Team number
        cfo: CFO name
        description: Issue description

    Returns:
        Tuple of (success: bool, error_message: str)
    """
    return db.report_student_issue(request_id, team, cfo, description)


def mark_received(request_id: int) -> None:
    """Mark a request as received by student.

    Args:
        request_id: Request ID
    """
    db.mark_received_by_student(request_id)


def send_nudge(request_id: int, team: str, cfo: str) -> tuple[bool, str]:
    """Send a nudge about a request.

    Args:
        request_id: Request ID
        team: Team number
        cfo: CFO name

    Returns:
        Tuple of (success: bool, error_message: str)
    """
    return db.record_student_nudge(request_id, team, cfo)


def update_request_by_coordinator(
    request_id: int,
    order_number: str,
    status: str,
    instructor_approval: str,
    coordinator_notes: str,
    student_issue_report: str = "",
) -> None:
    """Update a request from coordinator perspective.

    Args:
        request_id: Request ID
        order_number: Order number
        status: New status
        instructor_approval: Instructor approval text
        coordinator_notes: Coordinator notes
        student_issue_report: Student issue report text
    """
    db.update_request_coordinator(
        request_id,
        order_number,
        status,
        instructor_approval,
        coordinator_notes,
        student_issue_report=student_issue_report,
    )


def create_project(name: str) -> None:
    """Create a new project.

    Args:
        name: Project name
    """
    db.add_project(name)


def create_round(name: str, deadline_iso: str, project_id: int | None = None) -> None:
    """Create a new purchasing round.

    Args:
        name: Round name
        deadline_iso: Deadline in ISO format
        project_id: Optional project ID to link
    """
    db.add_round(name, deadline_iso, project_id)


def link_round_to_project(round_id: int, project_id: int | None) -> None:
    """Link a round to a project or unlink it.

    Args:
        round_id: Round ID
        project_id: Project ID or None to unlink
    """
    db.set_round_project(round_id, project_id)


def set_project_team_budget(project_id: int, budget_limit: float) -> None:
    """Set per-team budget limit for a project.

    Args:
        project_id: Project ID
        budget_limit: Budget limit in USD
    """
    db.set_project_team_budget(project_id, budget_limit)


def delete_project(project_id: int) -> None:
    """Delete a project.

    Args:
        project_id: Project ID
    """
    db.delete_project(project_id)
