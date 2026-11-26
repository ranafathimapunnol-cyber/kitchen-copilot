"""Excel and PDF renderings of the purchases-versus-payments report.

Both renderers take the report dictionary from
purchase_reports.build_purchases_vs_payments, the same data the screen
shows, and only lay it out. No figure is recalculated here: every amount,
count and total, including the total row, is the report's own value.

XlsxWriter and ReportLab are imported only when an export is made, so the
API still starts where they are not installed. PDFs use the bundled Noto
Sans fonts (app/assets/fonts), because PDF's built-in fonts have no Rupee
sign.
"""

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from app.core.clock import campus_timezone

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_REGULAR = "NotoSans"
FONT_BOLD = "NotoSans-Bold"

EXPORT_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}

TITLE = "Purchases vs payments"

METHOD_LABELS = {
    "CASH": "Cash",
    "BANK_TRANSFER": "Bank transfer",
    "UPI": "UPI",
    "CHEQUE": "Cheque",
    "OTHER": "Other",
}

# Excel: numeric cells with a Rupee format. A negative balance is an
# overpayment, shown as a credit, as on the screen.
XLSX_MONEY = '"₹"#,##0.00'
XLSX_BALANCE = '"₹"#,##0.00;"₹"#,##0.00" credit"'

SUPPLIER_COLUMNS = (
    "Supplier", "Owed at start", "Bills", "Billed", "Payments", "Paid",
    "of which cash", "Owed at end",
)


# ============================================================
# SHARED TEXT
# ============================================================

def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def group_indian(digits: str) -> str:
    """'1234567' → '12,34,567' (lakh and crore grouping, as en-IN)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def format_inr(value) -> str:
    """'1234567.5' → '₹12,34,567.50', the same text the screen shows."""
    amount = money(value)
    whole, fraction = format(abs(amount), "f").split(".")
    return f"{'-' if amount < 0 else ''}₹{group_indian(whole)}.{fraction}"


def format_balance(value) -> str:
    """A negative balance means the supplier was overpaid: a credit."""
    amount = money(value)
    return f"{format_inr(-amount)} credit" if amount < 0 else format_inr(amount)


def format_day(iso: str) -> str:
    """'2026-11-01' → '01 Nov 2026'."""
    return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d %b %Y")


def method_label(method: str) -> str:
    return METHOD_LABELS.get(method, method)


def period_text(report: dict) -> str:
    period = report["period"]
    return f"{format_day(period['date_from'])} – {format_day(period['date_to'])}"


def supplier_filter_text(report: dict) -> str:
    return report["filters"]["supplier_name"] or "All suppliers"


def generated_text(report: dict, exported_by: str) -> str:
    moment = datetime.fromisoformat(report["generated_at"]).astimezone(
        campus_timezone()
    )
    return f"{moment.strftime('%d %b %Y, %H:%M')} {moment.tzname()} by {exported_by}"


def header_rows(report: dict, exported_by: str) -> list[tuple[str, str]]:
    return [
        ("Campus", report["campus"]["name"] or f"Campus #{report['campus']['id']}"),
        ("Period", period_text(report)),
        ("Supplier", supplier_filter_text(report)),
        ("Currency", f"{report['currency']} (₹)"),
        ("Generated", generated_text(report, exported_by)),
    ]


def basis_lines(report: dict) -> list[str]:
    basis = report["basis"]
    return [
        f"Purchase expenditure: {basis['purchases']}",
        f"Supplier payments: {basis['payments']}",
        f"Balances: {basis['balances']}",
        f"Not included: {basis['excluded']}",
        "Owed at end = owed at start + billed − paid.",
    ]


def export_filename(report: dict, extension: str) -> str:
    period = report["period"]
    name = f"purchases-vs-payments_{period['date_from']}_{period['date_to']}"
    supplier = report["filters"]["supplier_name"]
    if supplier:
        slug = re.sub(r"[^a-z0-9]+", "-", supplier.lower()).strip("-")[:40]
        name += f"_{slug or 'supplier-' + str(report['filters']['supplier_id'])}"
    return f"{name}.{extension}"


# ============================================================
# EXCEL
# ============================================================

def render_xlsx(report: dict, exported_by: str) -> bytes:
    import xlsxwriter

    totals = report["totals"]
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    workbook.set_properties({
        "title": TITLE,
        "subject": f"{period_text(report)} · {supplier_filter_text(report)}",
        "author": exported_by,
        "company": report["campus"]["name"] or "",
        "comments": "Generated by Kitchen Copilot.",
    })

    title = workbook.add_format({"bold": True, "font_size": 14})
    label = workbook.add_format({"bold": True, "font_color": "#475569"})
    heading = workbook.add_format({"bold": True, "font_size": 12})
    column = workbook.add_format({
        "bold": True, "bg_color": "#F1F5F9", "bottom": 1, "text_wrap": True,
        "valign": "top",
    })
    column_right = workbook.add_format({
        "bold": True, "bg_color": "#F1F5F9", "bottom": 1, "align": "right",
        "text_wrap": True, "valign": "top",
    })
    note = workbook.add_format({"font_color": "#64748B", "italic": True})
    amount = workbook.add_format({"num_format": XLSX_MONEY})
    balance = workbook.add_format({"num_format": XLSX_BALANCE})
    total_text = workbook.add_format({"bold": True, "top": 1})
    total_count = workbook.add_format({"bold": True, "top": 1})
    total_amount = workbook.add_format({"bold": True, "top": 1, "num_format": XLSX_MONEY})
    total_balance = workbook.add_format({"bold": True, "top": 1, "num_format": XLSX_BALANCE})

    def number(value) -> float:
        # Report values are exact two-place decimals; Excel stores numbers
        # as doubles, which hold them exactly to well beyond ₹10^12.
        return float(money(value))

    # ---- Report sheet ----
    sheet = workbook.add_worksheet("Report")
    sheet.set_column(0, 0, 34)
    sheet.set_column(1, 1, 18)
    sheet.set_column(2, 2, 10)
    sheet.set_column(3, 3, 18)
    sheet.set_column(4, 4, 11)
    sheet.set_column(5, 7, 18)

    row = 0
    sheet.write(row, 0, TITLE, title)
    row += 1
    for key, value in header_rows(report, exported_by):
        sheet.write(row, 0, key, label)
        sheet.write(row, 1, value)
        row += 1

    row += 1
    sheet.write(row, 0, "Totals", heading)
    row += 1
    sheet.write_row(row, 0, ("Measure", "Count", "Amount"), column)
    sheet.write(row, 2, "Amount", column_right)
    row += 1
    summary = [
        ("Purchase expenditure (bills dated in the period)", totals["bill_count"], totals["billed"], amount),
        ("Supplier payments (payments dated in the period)", totals["payment_count"], totals["paid"], amount),
        ("of which cash", None, totals["paid_cash"], amount),
        ("Owed at start", None, totals["opening_balance"], balance),
        ("Owed at end", None, totals["closing_balance"], balance),
    ]
    for text, count, value, fmt in summary:
        sheet.write(row, 0, text)
        if count is not None:
            sheet.write_number(row, 1, count)
        sheet.write_number(row, 2, number(value), fmt)
        row += 1

    row += 1
    sheet.write(row, 0, "By supplier", heading)
    row += 1
    header_row = row
    for index, name in enumerate(SUPPLIER_COLUMNS):
        sheet.write(row, index, name, column if index == 0 else column_right)
    row += 1
    for supplier in report["suppliers"]:
        sheet.write(row, 0, supplier["supplier_name"] or f"Supplier #{supplier['supplier_id']}")
        sheet.write_number(row, 1, number(supplier["opening_balance"]), balance)
        sheet.write_number(row, 2, supplier["bill_count"])
        sheet.write_number(row, 3, number(supplier["billed"]), amount)
        sheet.write_number(row, 4, supplier["payment_count"])
        sheet.write_number(row, 5, number(supplier["paid"]), amount)
        sheet.write_number(row, 6, number(supplier["paid_cash"]), amount)
        sheet.write_number(row, 7, number(supplier["closing_balance"]), balance)
        row += 1
    if report["suppliers"]:
        sheet.autofilter(header_row, 0, row - 1, len(SUPPLIER_COLUMNS) - 1)
    else:
        sheet.write(row, 0, "No bills or payments in this period.", note)
        row += 1

    sheet.write(row, 0, "Total", total_text)
    sheet.write_number(row, 1, number(totals["opening_balance"]), total_balance)
    sheet.write_number(row, 2, totals["bill_count"], total_count)
    sheet.write_number(row, 3, number(totals["billed"]), total_amount)
    sheet.write_number(row, 4, totals["payment_count"], total_count)
    sheet.write_number(row, 5, number(totals["paid"]), total_amount)
    sheet.write_number(row, 6, number(totals["paid_cash"]), total_amount)
    sheet.write_number(row, 7, number(totals["closing_balance"]), total_balance)
    row += 2

    for line in basis_lines(report):
        sheet.write(row, 0, line, note)
        row += 1

    sheet.freeze_panes(header_row + 1, 1)

    # ---- Payment methods sheet ----
    methods = workbook.add_worksheet("Payment methods")
    methods.set_column(0, 0, 22)
    methods.set_column(1, 1, 12)
    methods.set_column(2, 2, 18)
    methods.write(0, 0, "Payments by method", title)
    methods.write(1, 0, f"{period_text(report)} · {supplier_filter_text(report)}", note)
    methods.write_row(3, 0, ("Method", "Payments"), column)
    methods.write(3, 2, "Amount", column_right)
    line = 4
    for entry in totals["paid_by_method"]:
        methods.write(line, 0, method_label(entry["payment_method"]))
        methods.write_number(line, 1, entry["payment_count"])
        methods.write_number(line, 2, number(entry["amount"]), amount)
        line += 1
    methods.write(line, 0, "Total paid", total_text)
    methods.write_number(line, 1, totals["payment_count"], total_count)
    methods.write_number(line, 2, number(totals["paid"]), total_amount)

    workbook.close()
    return buffer.getvalue()


# ============================================================
# PDF
# ============================================================

_fonts_registered = False


def _register_fonts() -> None:
    global _fonts_registered
    if _fonts_registered:
        return

    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(FONT_DIR / "NotoSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "NotoSans-Bold.ttf")))
    addMapping(FONT_REGULAR, 0, 0, FONT_REGULAR)
    addMapping(FONT_REGULAR, 1, 0, FONT_BOLD)
    _fonts_registered = True


def render_pdf(report: dict, exported_by: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.platypus import (
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _register_fonts()

    totals = report["totals"]
    ink = colors.HexColor("#0F172A")
    muted = colors.HexColor("#64748B")
    rule = colors.HexColor("#CBD5E1")
    band = colors.HexColor("#F1F5F9")

    base = ParagraphStyle("base", fontName=FONT_REGULAR, fontSize=9, leading=12, textColor=ink)
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=10.5, textColor=muted)
    title_style = ParagraphStyle("title", parent=base, fontName=FONT_BOLD, fontSize=16, leading=20)
    heading_style = ParagraphStyle(
        "heading", parent=base, fontName=FONT_BOLD, fontSize=11, leading=14,
        spaceBefore=8, spaceAfter=4,
    )

    def table_style(numeric_from: int, total_row: bool) -> TableStyle:
        commands = [
            ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("BACKGROUND", (0, 0), (-1, 0), band),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, rule),
            ("ALIGN", (numeric_from, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if total_row:
            commands += [
                ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, ink),
            ]
        return TableStyle(commands)

    story = [Paragraph(TITLE, title_style), Spacer(1, 3 * mm)]

    meta = Table(
        [[Paragraph(f"<b>{escape(key)}</b>", base), Paragraph(escape(value), base)]
         for key, value in header_rows(report, exported_by)],
        colWidths=[32 * mm, 200 * mm],
        hAlign="LEFT",
    )
    meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [meta, Spacer(1, 4 * mm)]

    summary = Table(
        [
            ["Measure", "Count", "Amount"],
            ["Purchase expenditure (bills dated in the period)",
             f"{totals['bill_count']} bills", format_inr(totals["billed"])],
            ["Supplier payments (payments dated in the period)",
             f"{totals['payment_count']} payments", format_inr(totals["paid"])],
            ["of which cash", "", format_inr(totals["paid_cash"])],
            ["Owed at start", "", format_balance(totals["opening_balance"])],
            ["Owed at end", "", format_balance(totals["closing_balance"])],
        ],
        colWidths=[110 * mm, 32 * mm, 40 * mm],
        hAlign="LEFT",
    )
    summary.setStyle(table_style(1, total_row=False))
    story += [KeepTogether([Paragraph("Totals", heading_style), summary])]

    methods = Table(
        [["Method", "Payments", "Amount"]]
        + [[method_label(m["payment_method"]), str(m["payment_count"]), format_inr(m["amount"])]
           for m in totals["paid_by_method"]]
        + [["Total paid", str(totals["payment_count"]), format_inr(totals["paid"])]],
        colWidths=[110 * mm, 32 * mm, 40 * mm],
        hAlign="LEFT",
    )
    methods.setStyle(table_style(1, total_row=True))
    story += [KeepTogether([Paragraph("Payments by method", heading_style), methods])]

    story.append(Paragraph("By supplier", heading_style))
    if report["suppliers"]:
        rows = [list(SUPPLIER_COLUMNS)]
        for supplier in report["suppliers"]:
            rows.append([
                Paragraph(escape(supplier["supplier_name"] or f"Supplier #{supplier['supplier_id']}"), base),
                format_balance(supplier["opening_balance"]),
                str(supplier["bill_count"]),
                format_inr(supplier["billed"]),
                str(supplier["payment_count"]),
                format_inr(supplier["paid"]),
                format_inr(supplier["paid_cash"]),
                format_balance(supplier["closing_balance"]),
            ])
        rows.append([
            "Total",
            format_balance(totals["opening_balance"]),
            str(totals["bill_count"]),
            format_inr(totals["billed"]),
            str(totals["payment_count"]),
            format_inr(totals["paid"]),
            format_inr(totals["paid_cash"]),
            format_balance(totals["closing_balance"]),
        ])
        suppliers = Table(
            rows,
            colWidths=[67 * mm, 33 * mm, 14 * mm, 32 * mm, 18 * mm, 32 * mm, 32 * mm, 39 * mm],
            repeatRows=1,
            hAlign="LEFT",
        )
        suppliers.setStyle(table_style(1, total_row=True))
        story.append(suppliers)
    else:
        story.append(Paragraph("No bills or payments in this period.", base))

    story.append(Spacer(1, 4 * mm))
    story += [Paragraph(escape(line), small) for line in basis_lines(report)]

    footer = (
        f"Kitchen Copilot · {TITLE} · {period_text(report)} · "
        f"{supplier_filter_text(report)}"
    )

    class NumberedCanvas(canvas.Canvas):
        """Adds "Page x of y" once the page count is known."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            count = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self.setFont(FONT_REGULAR, 7.5)
                self.setFillColor(muted)
                self.drawString(15 * mm, 9 * mm, footer)
                self.drawRightString(
                    landscape(A4)[0] - 15 * mm, 9 * mm,
                    f"Page {self._pageNumber} of {count}",
                )
                super().showPage()
            super().save()

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=TITLE,
        author=exported_by,
        subject=f"{report['campus']['name'] or ''} · {period_text(report)} · {supplier_filter_text(report)}",
        creator="Kitchen Copilot",
    )
    document.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
