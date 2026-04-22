# This app is a Streamlit app for student purchase requests and coordinator workflow.
# It organizes purchasing request both on the student and coordinator side.
# I manually changed the subtitle from "Coordinator dashboard- Dorothy" to "Coordinator dashboard (Dorothy)"

from __future__ import annotations

from datetime import date, datetime, time
from io import StringIO

import pandas as pd
import streamlit as st

import data
import utils

st.set_page_config(
    page_title="GIX Purchasing",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)


COORDINATOR_PASSWORD = data.load_coordinator_password()


def student_sidebar_budget(rounds: list[dict]) -> None:
    st.sidebar.subheader("Budget")
    team = st.sidebar.text_input(
        "Team number",
        key="sb_budget_team",
        help="Use the same team number as on your submission form.",
    )
    open_rounds = [r for r in rounds if data.check_round_is_open(r["deadline"])]
    if not open_rounds:
        st.sidebar.caption(
            "When a purchasing round is open and linked to a project, your team budget appears here."
        )
        return

    rid = st.sidebar.selectbox(
        "Open round (for project)",
        options=[r["id"] for r in open_rounds],
        format_func=lambda i: utils.format_round_label(next(x for x in open_rounds if x["id"] == i)),
        key="sb_budget_round",
    )
    if not str(team).strip():
        st.sidebar.caption("Enter your team number to see budget for the linked project.")
        return

    snap = data.get_budget_snapshot(str(team).strip(), int(rid))
    if snap is None:
        st.sidebar.info(
            "This round is not linked to a project. Your coordinator can link rounds under **Projects & budgets**."
        )
        return

    st.sidebar.markdown(f"**Project:** {snap['project_name']}")
    if not snap["budget_configured"]:
        st.sidebar.warning(
            "No budget is set for your team on this project yet. Ask your coordinator."
        )
        st.sidebar.metric("Total requested (all rounds in project)", f"${snap['total_requested']:,.2f}")
        return

    st.sidebar.metric("Team budget", f"${snap['budget_limit']:,.2f}")
    st.sidebar.metric("Total requested (all rounds)", f"${snap['total_requested']:,.2f}")
    st.sidebar.metric("Remaining", f"${snap['remaining']:,.2f}")
    if snap["over_budget"]:
        st.sidebar.error("Over budget: total requested exceeds your team limit.")
    elif snap.get("low_remaining"):
        st.sidebar.warning("Low remaining budget: under 20% of your team limit.")


def student_submit_view(rounds: list[dict]) -> None:
    open_rounds = [r for r in rounds if data.check_round_is_open(r["deadline"])]
    if not rounds:
        st.info("No purchasing rounds have been created yet. Please check back later.")
        return
    if not open_rounds:
        st.warning(
            "The submission window is closed for all current rounds (deadline has passed). "
            "Contact your program coordinator if you need help."
        )
        return

    st.subheader("New purchase line item")
    st.caption(
        "Choose an **open** round, then complete all required fields. "
        "After you submit, use **My status & tracking** with the same team and CFO to follow progress."
    )

    labels = {r["id"]: f"{r['name']} — deadline {r['deadline'][:16]}" for r in open_rounds}
    rid = st.selectbox(
        "Purchasing round",
        options=list(labels.keys()),
        format_func=lambda i: labels[i],
    )

    with st.form("student_request", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            team = st.text_input("Team number *", placeholder="e.g. 3")
            cfo = st.text_input("CFO name *", placeholder="Full name")
            supplier = st.selectbox("Supplier *", ["Amazon", "Non-Amazon"])
        with c2:
            item = st.text_input("Item name *")
            qty = st.number_input("Quantity *", min_value=1, value=1, step=1)
            unit = st.number_input("Unit price (USD) *", min_value=0.0, value=0.0, step=0.01, format="%.2f")

        link = st.text_input("Purchase link *", placeholder="https://...")
        notes = st.text_area("Notes (optional)", height=80)

        st.caption(
            "**Coordinator-only (after submission):** instructor approval, order number, and status. "
            "You can track these under **My status & tracking**."
        )

        submitted = st.form_submit_button("Submit request", type="primary")

        if submitted:
            missing = []
            if not str(team).strip():
                missing.append("Team number")
            if not str(cfo).strip():
                missing.append("CFO name")
            if not str(item).strip():
                missing.append("Item name")
            if not str(link).strip():
                missing.append("Purchase link")

            if missing:
                st.error("Please fill all required fields: " + ", ".join(missing))
            else:
                data.submit_purchase_request(
                    int(rid),
                    str(team).strip(),
                    str(cfo).strip(),
                    supplier,
                    str(item).strip(),
                    float(qty),
                    float(unit),
                    str(link).strip(),
                    notes,
                )
                st.success("Request submitted. Use **My status & tracking** with the same team and CFO to follow up.")


def student_tracking_view() -> None:
    st.subheader("Look up your requests")
    st.caption(
        "Use the **same team number and CFO name** you used on **Submit a request**. "
        "You’ll see status, coordinator notes, **Report an issue**, mark items received, or send a nudge."
    )
    if st.session_state.pop("track_nudge_success", None):
        st.success("Your coordinator has been notified.")
    if st.session_state.pop("issue_reported_flash", None):
        st.success("Issue reported. Your coordinator will follow up.")
    t1, t2, t3 = st.columns([2, 2, 1])
    with t1:
        team = st.text_input("Team number", key="track_team")
    with t2:
        cfo = st.text_input("CFO name", key="track_cfo")
    with t3:
        st.write("")
        st.write("")
        if st.button("Refresh", help="Reload status from the server"):
            st.rerun()

    if st.button("Show my requests", type="primary"):
        st.session_state["track_query"] = (team, cfo)

    pair = st.session_state.get("track_query")
    if not pair or not str(pair[0]).strip() or not str(pair[1]).strip():
        st.caption("Enter the same team number and CFO name you used when submitting.")
        return

    team_q, cfo_q = pair
    rows = data.get_requests_by_student(team_q, cfo_q)
    if not rows:
        st.info("No requests found for that team and CFO name.")
        return

    for r in rows:
        with st.container():
            st.subheader(f"Request #{r['id']} — {r.get('round_name', '')}")
            c_a, c_b = st.columns([2, 1])
            with c_a:
                st.write(
                    f"**Item:** {r['item_name']} × {r['quantity']} @ ${r['unit_price']:.2f} "
                    f"→ **${r['quantity'] * r['unit_price']:.2f}**"
                )
                st.write(f"**Supplier:** {r['supplier']}  |  **Submitted:** {r['submitted_at'][:19]}")
                if r.get("purchase_link"):
                    st.markdown(f"[Open purchase link]({r['purchase_link']})")
                if r.get("student_notes"):
                    st.caption(f"Your notes: {r['student_notes']}")
            with c_b:
                st.metric("Status", r["status"])
            if r.get("instructor_approval"):
                st.caption(f"Instructor approval: {r['instructor_approval']}")
            if r.get("order_number"):
                st.caption(f"Order number: {r['order_number']}")
            if r.get("coordinator_notes"):
                st.warning(f"**Coordinator note:** {r['coordinator_notes']}")
            if r.get("student_issue_report"):
                st.info(
                    f"**Issue on file** ({str(r.get('student_issue_reported_at') or '')[:19]}): "
                    f"{r['student_issue_report']}"
                )

            issue_key = f"issue_open_{r['id']}"
            if not st.session_state.get(issue_key, False):
                if st.button("Report an issue", key=f"issue_btn_{r['id']}"):
                    st.session_state[issue_key] = True
                    st.rerun()
            else:
                issue_desc = st.text_input(
                    "Describe the issue",
                    key=f"issue_desc_{r['id']}",
                    placeholder="Brief description for your coordinator",
                )
                if st.button("Submit issue", key=f"issue_submit_{r['id']}"):
                    ok, err = data.report_student_issue(
                        int(r["id"]), team_q, cfo_q, issue_desc
                    )
                    if ok:
                        st.session_state[issue_key] = False
                        st.session_state["track_query"] = (team_q, cfo_q)
                        st.session_state["issue_reported_flash"] = True
                        st.rerun()
                    else:
                        st.error(err)

            if r["status"] in ("Ordered", "Completed"):
                if st.button(
                    "Mark as received",
                    key=f"recv_{r['id']}",
                    help="Confirm you physically received this item",
                ):
                    data.mark_received(int(r["id"]))
                    st.session_state["track_query"] = (team_q, cfo_q)
                    st.rerun()
            elif r["status"] == "Received":
                st.success("This request is closed (received).")
            elif r["status"] in ("Pending", "Approved"):
                cooldown = data.get_seconds_until_next_nudge(r.get("last_nudged_at"))
                if cooldown > 0:
                    ch, cm = cooldown // 3600, (cooldown % 3600) // 60
                    st.caption(
                        f"You can send another nudge in {ch}h {cm}m."
                    )
                if st.button(
                    "Send a nudge",
                    key=f"nudge_{r['id']}",
                    help="Notify your coordinator about this request",
                    disabled=cooldown > 0,
                ):
                    ok, err = data.send_nudge(int(r["id"]), team_q, cfo_q)
                    if ok:
                        st.session_state["track_query"] = (team_q, cfo_q)
                        st.session_state["track_nudge_success"] = True
                        st.rerun()
                    else:
                        st.error(err)
            st.divider()


def student_view() -> None:
    utils.page_heading(
        "student",
        "Student Workspace",
        "Submit requests and track status.",
    )
    rounds = data.get_all_rounds()
    student_sidebar_budget(rounds)

    tab_a, tab_b = st.tabs(
        [
            "Submit a request",
            "My status & tracking",
        ]
    )
    with tab_a:
        student_submit_view(rounds)
    with tab_b:
        student_tracking_view()


def budget_overview_panel(project_id: int) -> None:
    st.caption("By team")
    rows = data.get_project_team_finance(project_id)
    if not rows:
        cap = data.get_project_team_budget_limit(project_id)
        if cap is not None:
            st.info(
                f"Per-team budget is **${cap:,.2f}** (same for every team). "
                "No purchase requests are recorded for this project’s rounds yet."
            )
        else:
            st.info(
                "No team activity yet. Set a per-team budget below and link rounds to this project."
            )
        return

    over_flags = [bool(r["over_budget"]) for r in rows]
    df = pd.DataFrame(
        [
            {
                "Team": r["team_number"],
                "Per-team budget": r["budget_limit"],
                "Total requested": r["total_requested"],
                "Spent (Ordered + Completed)": r["total_spent"],
                "Remaining": r["remaining"],
            }
            for r in rows
        ]
    )

    try:
        st.dataframe(
            df.style.apply(lambda row: utils.style_budget_row(row, over_flags), axis=1),
            use_container_width=True,
            hide_index=True,
        )
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True)
        for r in rows:
            if r["over_budget"]:
                st.error(f"Team {r['team_number']}: over budget (requested exceeds limit).")

    st.caption(
        "Remaining = budget limit − total requested (all submission line items in this project). "
        "Spent = sum of lines with status Ordered or Completed."
    )


def coordinator_summary(rows: list[dict]) -> None:
    total = len(rows)
    est = sum(r["quantity"] * r["unit_price"] for r in rows)
    pending_states = {"Pending", "Approved", "Ordered", "Needs Revision"}
    completed_states = {"Completed", "Received"}
    n_pending = sum(1 for r in rows if r["status"] in pending_states)
    n_done = sum(1 for r in rows if r["status"] in completed_states)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total requests", total)
    m2.metric("Estimated cost (USD)", f"${est:,.2f}")
    m3.metric("Pending / in progress", n_pending)
    m4.metric("Completed / received", n_done)


def coordinator_dashboard(round_id_filter: int | None) -> None:
    rows = data.get_all_requests(round_id_filter)
    st.subheader("Summary")
    coordinator_summary(rows)

    projects = data.get_all_projects()
    if projects:
        st.subheader("Budget overview")
        labels = {p["id"]: p["name"] for p in projects}
        bp = st.selectbox(
            "Budget overview — select project",
            options=[None] + list(labels.keys()),
            format_func=lambda x: "— choose project —" if x is None else labels[x],
            key="budget_project_pick",
        )
        if bp is not None:
            budget_overview_panel(int(bp))
    if not rows:
        st.info("No requests yet for this selection.")
        return

    df = pd.DataFrame(rows)
    if "last_nudged_at" not in df.columns:
        df["last_nudged_at"] = None

    df["nudge_ring"] = df["last_nudged_at"].map(utils.format_nudge_ring)
    df["line_total"] = df["quantity"] * df["unit_price"]
    display_cols = [
        "id",
        "nudge_ring",
        "project_name",
        "round_name",
        "team_number",
        "cfo_name",
        "supplier",
        "item_name",
        "quantity",
        "unit_price",
        "line_total",
        "purchase_link",
        "student_notes",
        "instructor_approval",
        "order_number",
        "status",
        "coordinator_notes",
        "student_issue_report",
        "student_issue_reported_at",
        "submitted_at",
        "received_at",
        "last_nudged_at",
    ]
    df = df[[c for c in display_cols if c in df.columns]]

    st.subheader("All requests")
    csv_buf = StringIO()
    df.to_csv(csv_buf, index=False)
    st.download_button(
        "Export CSV",
        data=csv_buf.getvalue(),
        file_name=f"gix_purchasing_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

    edited = st.data_editor(
        df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True, format="%d"),
            "nudge_ring": st.column_config.TextColumn("Nudge", disabled=True),
            "project_name": st.column_config.TextColumn("Project", disabled=True),
            "round_name": st.column_config.TextColumn("Round", disabled=True),
            "team_number": st.column_config.TextColumn("Team", disabled=True),
            "cfo_name": st.column_config.TextColumn("CFO", disabled=True),
            "supplier": st.column_config.TextColumn("Supplier", disabled=True),
            "item_name": st.column_config.TextColumn("Item", disabled=True),
            "quantity": st.column_config.NumberColumn("Qty", disabled=True),
            "unit_price": st.column_config.NumberColumn("Unit $", disabled=True, format="$%.2f"),
            "line_total": st.column_config.NumberColumn("Line total", disabled=True, format="$%.2f"),
            "purchase_link": st.column_config.LinkColumn("Purchase link", display_text="Open link"),
            "student_notes": st.column_config.TextColumn("Student notes", disabled=True),
            "instructor_approval": st.column_config.TextColumn("Instructor approval"),
            "order_number": st.column_config.TextColumn("Order #"),
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=list(data.ALL_STATUSES),
                required=True,
            ),
            "coordinator_notes": st.column_config.TextColumn("Coordinator notes"),
            "student_issue_report": st.column_config.TextColumn(
                "Student problem report (clear when resolved)"
            ),
            "student_issue_reported_at": st.column_config.TextColumn(
                "Report sent at (UTC)", disabled=True
            ),
            "submitted_at": st.column_config.TextColumn("Submitted", disabled=True),
            "received_at": st.column_config.TextColumn("Received at", disabled=True),
            "last_nudged_at": st.column_config.TextColumn("Last nudged (UTC)", disabled=True),
        },
        disabled=[
            "id",
            "nudge_ring",
            "project_name",
            "round_name",
            "team_number",
            "cfo_name",
            "supplier",
            "item_name",
            "quantity",
            "unit_price",
            "line_total",
            "purchase_link",
            "student_notes",
            "submitted_at",
            "received_at",
            "last_nudged_at",
        ],
        hide_index=True,
        num_rows="fixed",
        key="coord_editor",
        use_container_width=True,
    )

    if st.button("Save changes to database", type="primary"):
        for _, row in edited.iterrows():
            sir = row.get("student_issue_report")
            if sir is None or (isinstance(sir, float) and pd.isna(sir)):
                sir_s = ""
            else:
                sir_s = str(sir)
            data.update_request_by_coordinator(
                int(row["id"]),
                str(row.get("order_number") or ""),
                str(row["status"]),
                str(row.get("instructor_approval") or ""),
                str(row.get("coordinator_notes") or ""),
                student_issue_report=sir_s,
            )
        st.success("Saved.")
        st.rerun()


def coordinator_view() -> None:
    utils.page_heading(
        "coordinator",
        "GIX Purchasing",
        "Coordinator dashboard (Dorothy)",
    )

    st.header("Projects & budgets")
    with st.expander("Projects & budgets", expanded=True):
        p1, p2, p3, p4 = st.tabs(
            ["Create project", "Link rounds to project", "Per-team budget", "Delete project"]
        )
        with p1:
            pname = st.text_input("Project name", placeholder="e.g. Spring build — main project", key="new_proj_name")
            if st.button("Create project", key="btn_create_proj"):
                if not pname or not str(pname).strip():
                    st.error("Enter a project name.")
                else:
                    data.create_project(str(pname).strip())
                    st.success("Project created.")
                    st.rerun()
        with p2:
            projects = data.get_all_projects()
            rounds = data.get_all_rounds()
            if not projects:
                st.warning("Create a project first.")
            elif not rounds:
                st.info("Create a purchasing round first.")
            else:
                r_pick = st.selectbox(
                    "Round",
                    options=rounds,
                    format_func=lambda r: f"{r['name']} (project: {r.get('project_name') or '—'})",
                    key="link_round_sel",
                )
                proj_opts = {p["id"]: p["name"] for p in projects}
                cur_pid = r_pick.get("project_id")
                keys = list(proj_opts.keys())
                pid_choices = [None] + keys
                labels = ["— none —"] + [proj_opts[k] for k in keys]
                if cur_pid is None:
                    default_idx = 0
                elif cur_pid in keys:
                    default_idx = 1 + keys.index(cur_pid)
                else:
                    default_idx = 0
                sel = st.selectbox(
                    "Assign to project",
                    options=range(len(pid_choices)),
                    format_func=lambda i: labels[i],
                    index=default_idx,
                    key="link_proj_sel",
                )
                chosen_pid = pid_choices[sel]
                if st.button("Save assignment", key="btn_link_round"):
                    data.link_round_to_project(int(r_pick["id"]), chosen_pid)
                    st.success("Round updated.")
                    st.rerun()
        with p3:
            projects = data.get_all_projects()
            if not projects:
                st.warning("Create a project first.")
            else:
                proj_map = {p["id"]: p["name"] for p in projects}

                def proj_opt_label(pid: int) -> str:
                    name = proj_map[pid]
                    cap = next(
                        (p.get("team_budget_limit") for p in projects if p["id"] == pid),
                        None,
                    )
                    if cap is not None:
                        return f"{name} (per-team budget ${float(cap):,.2f})"
                    return f"{name} (no per-team budget set)"

                pid = st.selectbox(
                    "Project",
                    options=list(proj_map.keys()),
                    format_func=proj_opt_label,
                    key="tb_proj",
                )
                cur = next(
                    (p.get("team_budget_limit") for p in projects if p["id"] == pid),
                    None,
                )
                blim = st.number_input(
                    "Budget per team (USD) — same for every team in this project",
                    min_value=0.0,
                    value=float(cur) if cur is not None else 0.0,
                    step=50.0,
                    key="tb_limit",
                )
                if st.button("Save per-team budget", key="btn_tb"):
                    data.set_project_team_budget(int(pid), float(blim))
                    st.success("Saved. Every team in this project uses this same limit.")
                    st.rerun()
        with p4:
            projects_del = data.get_all_projects()
            if not projects_del:
                st.info("No projects to delete.")
            else:
                st.caption(
                    "Projects are listed by **ID** so duplicate names are easy to tell apart. "
                    "Deleting removes all team budgets for that project and unlinks any rounds "
                    "(rounds are kept; re-link them to another project if needed)."
                )
                del_map = {p["id"]: p for p in projects_del}

                del_id = st.selectbox(
                    "Project to delete",
                    options=[p["id"] for p in projects_del],
                    format_func=lambda pid: utils.format_project_label(pid, del_map[pid]),
                    key="del_proj_sel",
                )
                confirm = st.checkbox(
                    "I understand this permanently deletes this project and its team budgets, "
                    "and unlinks linked rounds.",
                    key="del_proj_confirm",
                )
                if st.button("Delete project", type="primary", disabled=not confirm, key="btn_del_proj"):
                    data.delete_project(int(del_id))
                    st.success(f"Deleted project #{del_id}.")
                    st.rerun()

    st.header("Create a new purchasing round")
    with st.expander("Create a new purchasing round", expanded=False):
        n1, n2, n3, n4 = st.columns([2, 1, 1, 2])
        projects = data.get_all_projects()
        proj_for_round: int | None = None
        with n1:
            rname = st.text_input("Round name", placeholder="e.g. Round 2 — Prototype parts")
        with n2:
            d = st.date_input("Deadline date", value=date.today())
        with n3:
            tm = st.time_input("Deadline time", value=time(17, 0))
        with n4:
            if projects:
                pm = {p["id"]: p["name"] for p in projects}
                pr_choices = [None] + list(pm.keys())
                ix = st.selectbox(
                    "Project",
                    options=range(len(pr_choices)),
                    format_func=lambda i: "— link later —" if pr_choices[i] is None else pm[pr_choices[i]],
                    key="round_proj_pick",
                )
                proj_for_round = pr_choices[ix]
            else:
                st.caption("Create a project above to link this round.")
        if st.button("Create round"):
            if not rname or not str(rname).strip():
                st.error("Enter a round name.")
            else:
                dt = datetime.combine(d, tm)
                data.create_round(str(rname).strip(), dt.isoformat(), proj_for_round)
                st.success("Round created.")
                st.rerun()

    rounds = data.get_all_rounds()
    if not rounds:
        st.info("Create a purchasing round to begin.")
        return

    st.header("Dashboard")

    opts = {"All rounds": None}
    for r in rounds:
        open_tag = "OPEN" if data.check_round_is_open(r["deadline"]) else "closed"
        opts[f"{r['name']} ({open_tag})"] = r["id"]

    choice = st.selectbox("Filter dashboard by round", list(opts.keys()))
    rid = opts[choice]

    coordinator_dashboard(rid)


def main() -> None:
    data.init_db()
    st.sidebar.title("GIX Purchasing")
    role = st.sidebar.radio(
        "I am a",
        ["Student", "Coordinator (Dorothy)"],
        horizontal=False,
    )

    if role.startswith("Coordinator"):
        st.sidebar.markdown("---")
        if st.session_state.get("coord_ok"):
            if st.sidebar.button("Sign out coordinator"):
                st.session_state.pop("coord_ok", None)
                st.rerun()
            coordinator_view()
        else:
            pwd = st.sidebar.text_input("Coordinator password", type="password")
            if st.sidebar.button("Sign in"):
                if pwd == COORDINATOR_PASSWORD:
                    st.session_state["coord_ok"] = True
                    st.rerun()
                else:
                    st.sidebar.error("Incorrect password.")
            st.sidebar.caption("Override the default password with `COORDINATOR_PASSWORD` in `.streamlit/secrets.toml`.")
            utils.page_heading(
                "student",
                "GIX Purchasing",
                "Sign in as coordinator using the sidebar",
            )
            return
    else:
        student_view()


if __name__ == "__main__":
    main()
