"""Build the four-page team-review report from prose and real public metrics."""
import json
from html import escape
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image


def main():
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 10
    styles["BodyText"].leading = 13
    flow = []
    text = Path("docs/report/experiments-and-results.md").read_text()
    sections = text.split("\n<!-- page -->\n")
    metrics = json.loads(Path("experiments/public/summary.json").read_text())
    for index, section in enumerate(sections):
        if index: flow.append(PageBreak())
        for para in section.split("\n\n"):
            para = para.strip()
            if not para: continue
            if para.strip() == "[RESULTS]":
                rows = [["Case", "P50 ms", "P95 ms", "P99 ms", "Fresh %", "Final %", "Fresh final %"]]
                for label, m in metrics.items():
                    rows.append([label]+[f"{m[k]:.2f}" for k in ["p50_ms","p95_ms","p99_ms","fresh_pct","final_completeness_pct","fresh_final_pct"]])
                t=Table(rows, repeatRows=1)
                t.setStyle(TableStyle([("FONTSIZE",(0,0),(-1,-1),8),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.grey),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
                flow.extend([t,Spacer(1,8)]);continue
            if para.strip() == "[FIGURE]":
                flow.append(Image("experiments/public/t5-cdf.png",width=420,height=210));continue
            heading=para.startswith("#")
            flow.extend([Paragraph(escape(para.lstrip("# ")).replace("\n"," "),styles["Heading2"] if heading else styles["BodyText"]),Spacer(1,6)])
    def footer(canvas,doc):
        canvas.setFont("Helvetica",8)
        canvas.drawString(40,25,"Team review draft: PR merges, contribution agreement and video pending")
        canvas.drawRightString(A4[0]-40,25,str(doc.page))
    SimpleDocTemplate("report.pdf",pagesize=A4,leftMargin=40,rightMargin=40,topMargin=35,bottomMargin=45,title="LiveRecall: design and public experiments").build(flow,onFirstPage=footer,onLaterPages=footer)


if __name__ == "__main__":
    main()
