from __future__ import annotations

from io import BytesIO

import xlsxwriter

from app.utils.pdf_export import build_pdf_report


def _base_formats(workbook: xlsxwriter.Workbook) -> dict[str, xlsxwriter.format.Format]:
    return {
        "title": workbook.add_format({"bold": True, "font_size": 20, "font_color": "#152235"}),
        "section": workbook.add_format({"bold": True, "font_size": 13, "font_color": "#152235", "bg_color": "#F7F9FC", "border": 1}),
        "label": workbook.add_format({"font_color": "#66768D", "font_size": 10}),
        "metric": workbook.add_format({"bold": True, "font_size": 16, "font_color": "#D72638", "border": 1, "align": "center"}),
        "table_head": workbook.add_format({"bold": True, "bg_color": "#152235", "font_color": "#FFFFFF", "border": 1}),
        "table_cell": workbook.add_format({"border": 1}),
        "table_pct": workbook.add_format({"border": 1, "num_format": "0%"}),
    }


def build_admin_report_xlsx(stats: dict) -> bytes:
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    formats = _base_formats(workbook)

    summary = workbook.add_worksheet("Summary")
    summary.hide_gridlines(2)
    summary.set_column("A:A", 28)
    summary.set_column("B:B", 16)
    summary.set_column("D:I", 15)
    summary.write("A1", "Admin Performance Report", formats["title"])

    metrics = [
        ("Objective Completion", stats["summary"]["objective_completion"] / 100),
        ("Workstream Completion", stats["summary"]["workstream_completion"] / 100),
        ("Activity Completion", stats["summary"]["activity_completion"] / 100),
        ("Task Completion", stats["summary"]["task_completion"] / 100),
    ]
    summary.write("A3", "Completion Snapshot", formats["section"])
    for idx, (label, value) in enumerate(metrics, start=4):
        summary.write(f"A{idx}", label, formats["label"])
        summary.write_number(f"B{idx}", value, formats["table_pct"])

    chart = workbook.add_chart({"type": "pie"})
    chart.add_series({
        "name": "Completion Mix",
        "categories": "=Summary!$A$4:$A$7",
        "values": "=Summary!$B$4:$B$7",
        "data_labels": {"percentage": True},
    })
    chart.set_title({"name": "Completion Mix"})
    chart.set_style(10)
    summary.insert_chart("D3", chart, {"x_scale": 1.25, "y_scale": 1.25})

    summary.write("A10", "Trend Analysis", formats["section"])
    summary.write_row("A11", ["Date", "Completed"], formats["table_head"])
    for row_index, point in enumerate(stats["trends"], start=12):
        summary.write(f"A{row_index}", point["date"].isoformat(), formats["table_cell"])
        summary.write_number(f"B{row_index}", point["completed"], formats["table_cell"])
    trend_chart = workbook.add_chart({"type": "column"})
    trend_chart.add_series({
        "name": "Completed Work",
        "categories": f"=Summary!$A$12:$A${11 + len(stats['trends'])}",
        "values": f"=Summary!$B$12:$B${11 + len(stats['trends'])}",
        "fill": {"color": "#D72638"},
    })
    trend_chart.set_title({"name": "7 Day Completion Trend"})
    trend_chart.set_style(12)
    summary.insert_chart("D10", trend_chart, {"x_scale": 1.3, "y_scale": 1.2})

    employees = workbook.add_worksheet("Employee Productivity")
    employees.hide_gridlines(2)
    employees.set_column("A:B", 24)
    employees.set_column("C:G", 14)
    employees.write_row("A1", ["Employee", "Email", "Assigned", "Completed", "Overdue", "Avg Progress", "Completion Rate"], formats["table_head"])
    for row_index, row in enumerate(stats["employee_productivity"], start=2):
        employees.write_row(
            row_index - 1,
            0,
            [
                row["user"].full_name,
                row["user"].email,
                row["assigned"],
                row["completed"],
                row["overdue"],
                row["avg_progress"] / 100,
                row["completion_rate"] / 100,
            ],
            formats["table_cell"],
        )
    employees.set_column("F:G", 14, formats["table_pct"])

    teams = workbook.add_worksheet("Team Performance")
    teams.hide_gridlines(2)
    teams.set_column("A:E", 18)
    teams.write_row("A1", ["Team", "Active Members", "Objective Completion", "Task Completion", "Overdue"], formats["table_head"])
    for row_index, row in enumerate(stats["team_performance"], start=2):
        teams.write_row(
            row_index - 1,
            0,
            [
                row["team"].name,
                row["active_members"],
                row["objective_completion"] / 100,
                row["task_completion"] / 100,
                row["overdue"],
            ],
            formats["table_cell"],
        )
    teams.set_column("C:D", 18, formats["table_pct"])

    workbook.close()
    return buffer.getvalue()


def build_manager_report_xlsx(stats: dict) -> bytes:
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    formats = _base_formats(workbook)

    summary = workbook.add_worksheet("Analytics")
    summary.hide_gridlines(2)
    summary.set_column("A:A", 24)
    summary.set_column("B:B", 14)
    summary.set_column("D:I", 14)
    summary.write("A1", "Employee Analytics Report", formats["title"])
    summary.write("A3", "Scope", formats["label"])
    summary.write("B3", stats["scope_label"], formats["table_cell"])
    summary.write("A5", "Status Mix", formats["section"])
    summary.write_row("A6", ["Status", "Count"], formats["table_head"])
    row_cursor = 7
    for label, count in stats["status_counts"].items():
        summary.write(f"A{row_cursor}", label, formats["table_cell"])
        summary.write_number(f"B{row_cursor}", count, formats["table_cell"])
        row_cursor += 1
    chart = workbook.add_chart({"type": "doughnut"})
    chart.add_series({
        "name": "Work Status Mix",
        "categories": f"=Analytics!$A$7:$A${row_cursor - 1}",
        "values": f"=Analytics!$B$7:$B${row_cursor - 1}",
        "data_labels": {"percentage": True},
    })
    chart.set_title({"name": "Work Status Mix"})
    chart.set_style(10)
    summary.insert_chart("D5", chart, {"x_scale": 1.2, "y_scale": 1.2})

    employees = workbook.add_worksheet("Workload")
    employees.hide_gridlines(2)
    employees.set_column("A:B", 24)
    employees.set_column("C:I", 14)
    employees.write_row("A1", ["Employee", "Email", "Assigned", "Open", "In Progress", "Blocked", "Overdue", "Completed", "Completion Rate"], formats["table_head"])
    for row_index, row in enumerate(stats["employees"], start=2):
        employees.write_row(
            row_index - 1,
            0,
            [
                row["employee"].full_name,
                row["employee"].email,
                row["assigned"],
                row["open"],
                row["in_progress"],
                row["blocked"],
                row["overdue"],
                row["completed"],
                row["completion_rate"] / 100,
            ],
            formats["table_cell"],
        )
    employees.set_column("I:I", 16, formats["table_pct"])

    workbook.close()
    return buffer.getvalue()


def build_audit_xlsx(logs: list) -> bytes:
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    formats = _base_formats(workbook)
    sheet = workbook.add_worksheet("Audit Logs")
    sheet.hide_gridlines(2)
    sheet.set_column("A:F", 24)
    sheet.write("A1", "Audit Log Export", formats["title"])
    sheet.write_row("A3", ["Timestamp", "Actor", "Action", "Entity", "Entity ID", "Details"], formats["table_head"])
    for row_index, log in enumerate(logs, start=4):
        sheet.write_row(
            row_index - 1,
            0,
            [
                log.created_at.isoformat(),
                log.actor.full_name if log.actor else "System",
                log.action,
                log.entity_type,
                log.entity_id or "",
                str(log.details or {}),
            ],
            formats["table_cell"],
        )
    workbook.close()
    return buffer.getvalue()


def build_admin_report_pdf(stats: dict) -> bytes:
    lines = [
        "Executive Summary",
        f'Objective completion: {stats["summary"]["objective_completion"]}%',
        f'Workstream completion: {stats["summary"]["workstream_completion"]}%',
        f'Activity completion: {stats["summary"]["activity_completion"]}%',
        f'Task completion: {stats["summary"]["task_completion"]}%',
        f'Overdue work: {stats["summary"]["overdue_work"]}',
        "",
        "Completion Trend",
    ]
    for point in stats["trends"]:
        lines.append(f'{point["date"].isoformat()}  {"#" * max(point["completed"], 1)}  ({point["completed"]})')
    lines.extend(["", "Team Performance"])
    for row in stats["team_performance"][:10]:
        lines.append(
            f'{row["team"].name}: members {row["active_members"]}, objective {row["objective_completion"]}%, '
            f'task {row["task_completion"]}%, overdue {row["overdue"]}'
        )
    return build_pdf_report(title="Admin Performance Report", lines=lines)


def build_manager_report_pdf(stats: dict) -> bytes:
    lines = [
        f'Scope: {stats["scope_label"]}',
        "",
        "Status Mix",
    ]
    for label, count in stats["status_counts"].items():
        lines.append(f"{label}: {count}")
    lines.extend(["", "Employee Productivity"])
    for row in stats["employees"][:12]:
        lines.append(
            f'{row["employee"].full_name}: assigned {row["assigned"]}, completed {row["completed"]}, '
            f'blocked {row["blocked"]}, overdue {row["overdue"]}, completion {row["completion_rate"]}%'
        )
    return build_pdf_report(title="Employee Analytics Report", lines=lines)


def build_audit_pdf(logs: list) -> bytes:
    lines = ["Audit Timeline"]
    for log in logs:
        lines.append(
            f'{log.created_at.isoformat()} | {log.actor.full_name if log.actor else "System"} | '
            f'{log.action} | {log.entity_type} #{log.entity_id or "-"}'
        )
    return build_pdf_report(title="Audit Log Export", lines=lines)
