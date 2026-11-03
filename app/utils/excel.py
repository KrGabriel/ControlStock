"""Exportacion profesional de informes a Excel."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.utils.dates import fmt_datetime

NAVY = "0F172A"
BLUE = "1D4ED8"
LIGHT_BLUE = "E0EAFF"
LIGHT_GRAY = "F1F5F9"
AMBER = "FEF3C7"
GREEN = "DCFCE7"
GRAY = "E2E8F0"
WHITE = "FFFFFF"

THIN = Side(style="thin", color="CBD5E1")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _safe_sheet_name(name: str, used: set[str]) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", name).strip() or "Hoja"
    cleaned = cleaned[:31]
    candidate = cleaned
    counter = 2
    while candidate.lower() in used:
        suffix = f" {counter}"
        candidate = f"{cleaned[: 31 - len(suffix)]}{suffix}"
        counter += 1
    used.add(candidate.lower())
    return candidate


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _write_title(ws: Worksheet, report: dict, last_col: int) -> int:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    cell = ws.cell(row=1, column=1, value=report.get("title", "Informe"))
    cell.fill = PatternFill("solid", fgColor=NAVY)
    cell.font = Font(bold=True, color=WHITE, size=15)
    cell.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[1].height = 30

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    subtitle = report.get("subtitle", "")
    cell = ws.cell(row=2, column=1, value=subtitle)
    cell.font = Font(bold=True, color=NAVY, size=11)
    cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
    cell.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[2].height = 20

    filters = report.get("filters") or []
    filter_text = "    ".join(f"{key}: {value}" for key, value in filters)
    generated = report.get("generated_at")
    generated_text = (
        f"Generado: {fmt_datetime(generated)}" if isinstance(generated, datetime) else ""
    )
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=last_col)
    cell = ws.cell(row=3, column=1, value=" | ".join(x for x in (filter_text, generated_text) if x))
    cell.font = Font(italic=True, color="475569", size=10)
    cell.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    return 5


def _style_header(ws: Worksheet, row: int, columns: list[str]) -> None:
    fill = PatternFill("solid", fgColor=BLUE)
    for index, column in enumerate(columns, start=1):
        cell = ws.cell(row=row, column=index, value=column)
        cell.fill = fill
        cell.font = Font(bold=True, color=WHITE, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[row].height = 30


def _status_fill(value) -> PatternFill | None:
    if not isinstance(value, str):
        return None
    text = value.lower()
    if "pendiente" in text:
        return PatternFill("solid", fgColor=AMBER)
    if "cargada" in text or "vigente" in text:
        return PatternFill("solid", fgColor=GREEN)
    if "anulado" in text or "anulada" in text:
        return PatternFill("solid", fgColor=GRAY)
    return None


def _write_section_sheet(wb: Workbook, report: dict, section: dict, used_names: set[str]) -> None:
    columns = list(section.get("columns") or [])
    rows = list(section.get("rows") or [])
    if not columns:
        return
    ws = wb.create_sheet(_safe_sheet_name(section.get("title", "Seccion"), used_names))
    ws.sheet_view.showGridLines = False
    last_col = len(columns)
    header_row = _write_title(ws, report, last_col)

    section_name = section.get("title", "")
    if section_name:
        ws.merge_cells(
            start_row=header_row - 1, start_column=1, end_row=header_row - 1, end_column=last_col
        )
        cell = ws.cell(row=header_row - 1, column=1, value=section_name)
        cell.font = Font(bold=True, color=NAVY, size=12)
        cell.alignment = Alignment(vertical="center", horizontal="left", indent=1)

    _style_header(ws, header_row, columns)
    row_index = header_row + 1
    for data_row in rows:
        for col_index, value in enumerate(data_row, start=1):
            cell = ws.cell(row=row_index, column=col_index)
            if isinstance(value, datetime):
                cell.value = value
                cell.number_format = "dd/mm/yyyy hh:mm"
                cell.alignment = Alignment(horizontal="center", vertical="top")
            elif isinstance(value, date):
                cell.value = value
                cell.number_format = "dd/mm/yyyy"
                cell.alignment = Alignment(horizontal="center", vertical="top")
            else:
                cell.value = value
                if _is_number(value):
                    cell.number_format = "#,##0"
                    cell.alignment = Alignment(horizontal="right", vertical="top")
                else:
                    cell.alignment = Alignment(
                        horizontal="left",
                        vertical="top",
                        wrap_text=isinstance(value, str) and len(value) > 45,
                    )
            cell.border = BORDER
            cell.font = Font(size=10)
            fill = _status_fill(value)
            if fill is not None:
                cell.fill = fill
        if row_index % 2 == 0:
            for col_index in range(1, last_col + 1):
                cell = ws.cell(row=row_index, column=col_index)
                if cell.fill.fgColor.rgb in (None, "00000000"):
                    cell.fill = PatternFill("solid", fgColor=LIGHT_GRAY)
        row_index += 1

    last_data_row = row_index - 1
    if section.get("totals") and rows:
        totals_row = [""] * last_col
        totals_row[0] = "TOTAL"
        numeric_columns = [
            index
            for index in range(1, last_col)
            if any(_is_number(row[index]) for row in rows if len(row) > index)
        ]
        for index in numeric_columns:
            totals_row[index] = sum(
                row[index] for row in rows if len(row) > index and _is_number(row[index])
            )
        for col_index, value in enumerate(totals_row, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.font = Font(bold=True, color=NAVY, size=10)
            cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
            cell.border = BORDER
            if _is_number(value):
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
        row_index += 1

    custom_total = section.get("totals_row")
    if custom_total:
        for col_index, value in enumerate(custom_total, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.font = Font(bold=True, color=NAVY, size=10)
            cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
            cell.border = BORDER
            if _is_number(value):
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
        row_index += 1

    if rows:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(last_col)}{last_data_row}"
    ws.freeze_panes = f"A{header_row + 1}"

    for col_index, column in enumerate(columns, start=1):
        values = [column] + [
            fmt_datetime(row[col_index - 1])
            if isinstance(row[col_index - 1], datetime)
            else str(row[col_index - 1] or "")
            for row in rows
            if len(row) >= col_index
        ]
        width = max(len(str(value)) for value in values) + 3
        if "Observ" in column or "Motivo" in column or "Articulos" in column:
            width = max(width, 28)
        ws.column_dimensions[get_column_letter(col_index)].width = min(max(width, 10), 48)

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"


def _write_summary_sheet(wb: Workbook, report: dict, used_names: set[str]) -> None:
    ws = wb.create_sheet(_safe_sheet_name("Resumen", used_names))
    ws.sheet_view.showGridLines = False
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    cell = ws.cell(row=1, column=1, value=report.get("title", "Informe"))
    cell.fill = PatternFill("solid", fgColor=NAVY)
    cell.font = Font(bold=True, color=WHITE, size=15)
    cell.alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[1].height = 30

    ws["A3"] = "Periodo / filtros"
    ws["A3"].font = Font(bold=True, color=NAVY)
    ws["B3"] = report.get("subtitle", "")
    ws["A4"] = "Generado"
    ws["A4"].font = Font(bold=True, color=NAVY)
    generated = report.get("generated_at")
    ws["B4"] = generated if isinstance(generated, datetime) else str(generated or "")
    if isinstance(ws["B4"].value, datetime):
        ws["B4"].number_format = "dd/mm/yyyy hh:mm"
    ws["A5"] = "Secciones incluidas"
    ws["A5"].font = Font(bold=True, color=NAVY)
    ws["B5"] = len(report.get("sections") or [])

    start = 7
    _style_header(ws, start, ["Seccion", "Filas", "Columnas"])
    row = start + 1
    for section in report.get("sections") or []:
        ws.cell(row=row, column=1, value=section.get("title", ""))
        ws.cell(row=row, column=2, value=len(section.get("rows") or []))
        ws.cell(row=row, column=3, value=", ".join(section.get("columns") or []))
        for col in range(1, 4):
            ws.cell(row=row, column=col).border = BORDER
            ws.cell(row=row, column=col).alignment = Alignment(vertical="top", wrap_text=col == 3)
        row += 1
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 80
    ws.column_dimensions["D"].width = 12


def export_report_to_excel(report: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    default = wb.active
    wb.remove(default)
    wb.properties.title = report.get("title", "Informe ControlStock")
    wb.properties.creator = "ControlStock"
    wb.properties.description = report.get("subtitle", "")
    used_names: set[str] = set()
    _write_summary_sheet(wb, report, used_names)
    for section in report.get("sections") or []:
        if section.get("rows") or section.get("columns"):
            _write_section_sheet(wb, report, section, used_names)
    wb.active = 0
    wb.save(path)
    return path
