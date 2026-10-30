"""Local-only Markdown presentation for downloadable run reports."""

import re
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)


def inline(text: str) -> str:
    """Allow only generated presentation tags; never interpret source HTML."""

    parts = re.split(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|!?\[[^\]]*\]\([^)]+\))", text)
    result: list[str] = []

    for part in parts:
        if part.startswith("`") and part.endswith("`"):
            result.append(f'<font backColor="#eef2f6">{escape(part[1:-1])}</font>')
        elif part.startswith("**") and part.endswith("**"):
            result.append(f"<b>{escape(part[2:-2])}</b>")
        elif part.startswith("*") and part.endswith("*"):
            result.append(f"<i>{escape(part[1:-1])}</i>")
        elif match := re.fullmatch(r"!?\[([^\]]*)\]\(([^)]+)\)", part):
            result.append(escape(f"{match[1]} ({match[2]})"))
        else:
            result.append(escape(part))

    return "".join(result)


def markdown_story(report: str, font: str, width: float) -> list[Flowable]:
    """Render common report blocks, with oversized cells and code able to split."""

    body = ParagraphStyle(
        "Body",
        fontName=font,
        fontSize=10,
        leading=15,
        spaceAfter=7,
        splitLongWords=True,
    )
    code = ParagraphStyle(
        "Code",
        parent=body,
        fontSize=8,
        leading=11,
        leftIndent=10,
        rightIndent=10,
        backColor=colors.HexColor("#eef2f6"),
        spaceAfter=0,
    )
    cell = ParagraphStyle("Cell", parent=body, fontSize=8, leading=12, spaceAfter=0)
    story: list[Flowable] = []
    lines = report.splitlines()
    index = 0
    fence: str | None = None

    while index < len(lines):
        line = lines[index]
        index += 1

        if marker := re.match(r"^\s{0,3}(`{3,}|~{3,})", line):
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
                story.append(Spacer(1, 8))
            else:
                story.append(Paragraph(escape(line), code))

            continue

        if fence is not None:
            # Separate code lines can paginate; nonbreaking spaces preserve indentation.
            text = escape(line.expandtabs(4)).replace(" ", "&#160;") or "&#160;"
            story.append(Paragraph(text, code))
            continue

        if not line.strip():
            continue

        if (
            "|" in line
            and index < len(lines)
            and re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*", lines[index])
        ):
            rows = [line]
            index += 1

            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(lines[index])
                index += 1

            values = [re.split(r"(?<!\\)\|", row.strip().strip("|")) for row in rows]
            columns = max(len(row) for row in values)
            data = [
                [Paragraph(inline(value.strip().replace(r"\|", "|")), cell) for value in row]
                + [Paragraph("", cell)] * (columns - len(row))
                for row in values
            ]
            table = LongTable(
                data,
                colWidths=[width / columns] * columns,
                repeatRows=1,
                splitByRow=0,
                splitInRow=1,
                hAlign="LEFT",
                spaceAfter=10,
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(table)
            continue

        if heading := re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line):
            level = len(heading[1])
            size = {1: 23, 2: 16, 3: 12}.get(level, 11)
            style = ParagraphStyle(
                f"Heading{level}",
                parent=body,
                fontSize=size,
                leading=size + 5,
                spaceBefore=14,
                spaceAfter=9,
                keepWithNext=True,
                textColor=colors.HexColor("#0f172a"),
            )
            story.append(Paragraph(inline(heading[2]), style))
        elif re.fullmatch(r"\s*(---+|\*\*\*+|___+)\s*", line):
            story.append(HRFlowable(width="100%", color=colors.HexColor("#cbd5e1")))
        elif item := re.match(r"^(\s*)([-+*]|\d+[.)])\s+(.+)$", line):
            indent = min(len(item[1]), 16) * 5
            style = ParagraphStyle(
                "List",
                parent=body,
                leftIndent=15 + indent,
                firstLineIndent=-10,
            )
            label = "•" if item[2] in "-+*" else item[2]
            story.append(Paragraph(f"{escape(label)} {inline(item[3])}", style))
        elif line.startswith(">"):
            style = ParagraphStyle("Quote", parent=body, leftIndent=14)
            story.append(Paragraph(inline(line.lstrip("> ")), style))
        else:
            story.append(Paragraph(inline(line), body))

    return story or [Paragraph("No report content.", body)]


def build_pdf(report: str, font: str) -> bytes:
    """Use consistent A4 margins and a repeated page footer."""

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        title="Workflow run report",
        author="AgentFlow",
        leftMargin=44,
        rightMargin=44,
        topMargin=38,
        bottomMargin=46,
    )

    def footer(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(doc.leftMargin, 24, "AgentFlow | Workflow run report")
        canvas.drawRightString(A4[0] - doc.rightMargin, 24, f"Page {doc.page}")
        canvas.restoreState()

    document.build(
        markdown_story(report, font, document.width),
        onFirstPage=footer,
        onLaterPages=footer,
    )

    return output.getvalue()
