"""Helper functions for formatting, styling, and display logic."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def inject_style(role: str) -> None:
    """Inject CSS styles based on user role (student or coordinator).

    Args:
        role: Either "student" or "coordinator"
    """
    if role == "coordinator":
        accent = "#0d6e5c"
        bg = "#f0faf8"
        student_tab_css = ""
    else:
        accent = "#1e5a8a"
        bg = "#f2f7fc"
        student_tab_css = """
        /* Emphasize main student tasks (tabs) in the information hierarchy */
        div[data-testid="stTabs"] [data-baseweb="tab-list"] button p {
            font-size: 1.2rem !important;
            font-weight: 650 !important;
            letter-spacing: -0.01em;
        }
        div[data-testid="stTabs"] [data-baseweb="tab-list"] button {
            padding-top: 0.65rem !important;
            padding-bottom: 0.65rem !important;
        }
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            height: 4px !important;
        }
        """
    st.markdown(
        f"""
        <style>
        .block-container {{ padding-top: 1.2rem; }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {bg} 0%, #ffffff 55%);
            border-right: 3px solid {accent};
        }}
        {student_tab_css}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_heading(role: str, title: str, subtitle: str) -> None:
    """Display page heading with role-based styling.

    Args:
        role: Either "student" or "coordinator"
        title: Main page title
        subtitle: Subtitle/caption
    """
    inject_style(role)
    st.title(title)
    st.caption(subtitle)


def format_nudge_ring(v: object) -> str:
    """Format nudge ring indicator for dataframe cells.

    Args:
        v: Value from last_nudged_at column

    Returns:
        "⭕" if value is present, empty string otherwise
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "⭕" if s else ""


def style_budget_row(row: pd.Series, over_budget_flags: list[bool]) -> list[str]:
    """Style dataframe row based on budget status.

    Args:
        row: DataFrame row
        over_budget_flags: List of boolean flags indicating over-budget rows

    Returns:
        List of CSS style strings for each column
    """
    i = int(row.name)
    if i < len(over_budget_flags) and over_budget_flags[i]:
        return ["background-color: #ffcccc"] * len(row)
    return [""] * len(row)


def format_round_label(round_dict: dict, project_name: str | None = None) -> str:
    """Format a round label with project info.

    Args:
        round_dict: Round dictionary with 'name' key
        project_name: Optional project name to include

    Returns:
        Formatted label string
    """
    pn = round_dict.get("project_name") or ""
    extra = f" — {pn}" if pn else " — (not linked to a project)"
    return f"{round_dict['name']}{extra}"


def format_project_label(project_id: int, project_dict: dict) -> str:
    """Format a project label with budget info.

    Args:
        project_id: Project ID
        project_dict: Project dictionary with 'id' and 'name' keys

    Returns:
        Formatted label string
    """
    return f"#{project_dict['id']} — {project_dict['name']}"
