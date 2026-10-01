from pathlib import Path
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    Image,
)
from reportlab.graphics.shapes import Drawing, String, Rect
from reportlab.graphics.charts.piecharts import Pie


class PDFGenerator:
    """Generate a styled PDF report for GitHub repository analysis."""

    NAVY = colors.HexColor("#17365D")
    BLUE = colors.HexColor("#2563EB")
    TEAL = colors.HexColor("#0F766E")
    CYAN = colors.HexColor("#0891B2")
    PURPLE = colors.HexColor("#7C3AED")
    GREEN = colors.HexColor("#16A34A")
    AMBER = colors.HexColor("#D97706")
    RED = colors.HexColor("#DC2626")
    LIGHT = colors.HexColor("#F1F5F9")
    PALE_BLUE = colors.HexColor("#EAF2FF")
    TEXT = colors.HexColor("#263445")
    MUTED = colors.HexColor("#64748B")
    BORDER = colors.HexColor("#D9E2EF")
    WHITE = colors.white

    def _styles(self):
        """Create report typography styles."""
        styles = getSampleStyleSheet()

        styles.add(ParagraphStyle(
            name="CoverTitleCustom",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=31,
            alignment=TA_CENTER,
            textColor=self.NAVY,
            spaceAfter=14,
        ))

        styles.add(ParagraphStyle(
            name="CoverSubtitleCustom",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=18,
            alignment=TA_CENTER,
            textColor=self.MUTED,
            spaceAfter=8,
        ))

        styles.add(ParagraphStyle(
            name="SectionHeadingCustom",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=self.NAVY,
            spaceBefore=13,
            spaceAfter=8,
            keepWithNext=True,
        ))

        styles.add(ParagraphStyle(
            name="SubheadingCustom",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=self.BLUE,
            spaceBefore=7,
            spaceAfter=4,
            keepWithNext=True,
        ))

        styles.add(ParagraphStyle(
            name="BodyCustom",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=self.TEXT,
            spaceAfter=5,
            alignment=TA_LEFT,
            splitLongWords=True,
        ))

        styles.add(ParagraphStyle(
            name="SmallCustom",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=self.MUTED,
            spaceAfter=3,
            splitLongWords=True,
        ))

        styles.add(ParagraphStyle(
            name="TableHeaderCustom",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=self.WHITE,
        ))

        styles.add(ParagraphStyle(
            name="TableCellCustom",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=self.TEXT,
            splitLongWords=True,
        ))

        styles.add(ParagraphStyle(
            name="ScoreCustom",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=32,
            alignment=TA_CENTER,
            textColor=self.NAVY,
        ))

        return styles

    @staticmethod
    def _safe_dict(value):
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _safe_list(value):
        if isinstance(value, (list, tuple)):
            return list(value)
        if value is None:
            return []
        return [value]

    @staticmethod
    def _safe_int(value, default=0):
        try:
            return max(0, int(value))
        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _plain_text(value):
        """Convert nested values into readable plain text."""
        if isinstance(value, dict):
            return "; ".join(
                f"{key}: {PDFGenerator._plain_text(item)}"
                for key, item in value.items()
            )

        if isinstance(value, (list, tuple, set)):
            return ", ".join(
                PDFGenerator._plain_text(item)
                for item in value
            )

        return str(value or "")

    def _paragraph(self, value, styles, style="BodyCustom"):
        """Create an escaped paragraph safe for ReportLab markup."""
        text = self._plain_text(value).strip()
        if not text:
            text = "Unavailable"

        return Paragraph(
            escape(text).replace("\n", "<br/>"),
            styles[style],
        )

    def _section(self, title, story, styles):
        story.append(
            Paragraph(escape(title), styles["SectionHeadingCustom"])
        )

    def _bullet_list(self, items, story, styles, empty_text="No information available."):
        """Render a safely escaped bulleted list."""
        items = self._safe_list(items)

        if not items:
            story.append(self._paragraph(empty_text, styles, "SmallCustom"))
            return

        for item in items:
            if isinstance(item, dict):
                item = self._plain_text(item)

            story.append(Paragraph(
                "• " + escape(str(item)),
                styles["BodyCustom"],
            ))

    def _table(self, rows, widths, styles, repeat_rows=1):
        """Build a consistently styled table with wrapped text."""
        formatted_rows = []

        for row_index, row in enumerate(rows):
            formatted_row = []
            for cell in row:
                if isinstance(cell, Paragraph):
                    formatted_row.append(cell)
                elif row_index == 0:
                    formatted_row.append(
                        Paragraph(
                            escape(str(cell)),
                            styles["TableHeaderCustom"],
                        )
                    )
                else:
                    formatted_row.append(
                        Paragraph(
                            escape(self._plain_text(cell)),
                            styles["TableCellCustom"],
                        )
                    )
            formatted_rows.append(formatted_row)

        table = Table(
            formatted_rows,
            colWidths=widths,
            repeatRows=repeat_rows,
            hAlign="LEFT",
        )

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self.NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), self.WHITE),
            ("GRID", (0, 0), (-1, -1), 0.35, self.BORDER),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                self.WHITE,
                self.LIGHT,
            ]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))

        return table

    def _calculate_health(self, repository_info, analysis):
        """
        Calculate an explainable repository health heuristic.

        Uses repository-visible signals; it is not a code-quality audit.
        """
        docs = self._safe_list(analysis.get("documentation"))
        configs = self._safe_list(analysis.get("configuration_files"))
        structure = self._safe_dict(analysis.get("structure"))

        readme = analysis.get("readme") or repository_info.get("readme")
        readme_found = bool(
            repository_info.get("readme_found")
            or (isinstance(readme, str) and readme.strip())
            or (isinstance(readme, dict) and readme)
        )

        documentation_score = 0
        if readme_found:
            documentation_score += 15
        if docs:
            documentation_score += 10
        documentation_score = min(documentation_score, 25)

        structure_text = self._plain_text(structure).lower()
        config_text = self._plain_text(configs).lower()
        docs_text = self._plain_text(docs).lower()
        testing_text = f"{structure_text} {config_text} {docs_text}"

        testing_terms = (
            "test", "tests", "testing", "pytest", "unittest",
            "tox", "jest", "vitest", "mocha", "spec",
        )

        testing_score = 0
        if any(term in testing_text for term in testing_terms):
            testing_score += 15
        if any(
            term in config_text
            for term in ("pytest", "tox", "jest", "vitest", "unittest")
        ):
            testing_score += 10
        testing_score = min(testing_score, 25)

        configuration_score = min(len(configs) * 5, 20)

        folders = self._safe_list(
            structure.get("folders")
            or structure.get("directories")
            or structure.get("top_level_folders")
        )
        files = self._safe_list(
            structure.get("files")
            or structure.get("top_level_files")
        )

        organization_score = 0
        if folders:
            organization_score += 10
        if files:
            organization_score += 5
        if organization_score == 0 and structure_text.strip():
            organization_score = 5
        organization_score = min(organization_score, 15)

        commits = self._safe_int(
            repository_info.get(
                "total_commits",
                analysis.get("total_commits", 0),
            )
        )
        contributors = self._safe_int(
            repository_info.get(
                "total_contributors",
                analysis.get("total_contributors", 0),
            )
        )

        activity_score = 0
        if commits >= 1:
            activity_score += 8
        if commits >= 10:
            activity_score += 3
        if contributors >= 1:
            activity_score += 4
        activity_score = min(activity_score, 15)

        breakdown = {
            "Documentation": documentation_score,
            "Testing signals": testing_score,
            "Configuration": configuration_score,
            "Organization": organization_score,
            "Activity signals": activity_score,
        }

        return min(sum(breakdown.values()), 100), breakdown

    def _health_label(self, score):
        if score >= 80:
            return "Many of the measured repository signals are present."
        if score >= 50:
            return "Some measured signals are present; review the breakdown."
        return "Several measured signals were not detected in the available data."

    def _health_chart(self, breakdown):
        """Create a colorful horizontal bar chart using ReportLab shapes."""
        width = 450
        row_height = 30
        height = 38 + row_height * len(breakdown)
        drawing = Drawing(width, height)

        palette = [
            self.BLUE,
            self.TEAL,
            self.PURPLE,
            self.CYAN,
            self.AMBER,
        ]

        max_points = 25
        label_width = 125
        bar_width = 245

        drawing.add(String(
            0,
            height - 15,
            "Health category points (out of each category maximum)",
            fontName="Helvetica-Bold",
            fontSize=8,
            fillColor=self.MUTED,
        ))

        for index, (label, score) in enumerate(breakdown.items()):
            y = height - 42 - index * row_height
            color = palette[index % len(palette)]

            drawing.add(String(
                0,
                y + 5,
                label,
                fontName="Helvetica",
                fontSize=8,
                fillColor=self.TEXT,
            ))

            drawing.add(Rect(
                label_width,
                y,
                bar_width,
                13,
                fillColor=self.LIGHT,
                strokeColor=None,
            ))

            bar_length = bar_width * max(0, min(score, max_points)) / max_points

            drawing.add(Rect(
                label_width,
                y,
                bar_length,
                13,
                fillColor=color,
                strokeColor=None,
            ))

            drawing.add(String(
                label_width + bar_width + 9,
                y + 3,
                f"{score}/{max_points}",
                fontName="Helvetica-Bold",
                fontSize=8,
                fillColor=self.TEXT,
            ))

        return drawing

    def _language_pie_chart(self, languages):
        """Create a colorful pie chart for detected programming languages."""
        valid = []

        if isinstance(languages, dict):
            for name, count in languages.items():
                try:
                    count = float(count)
                except (TypeError, ValueError, OverflowError):
                    continue

                if count > 0:
                    valid.append((str(name), count))

        if not valid:
            return None

        valid.sort(key=lambda item: item[1], reverse=True)
        valid = valid[:8]

        width = 430
        height = 225
        drawing = Drawing(width, height)

        pie = Pie()
        pie.x = 15
        pie.y = 18
        pie.width = 185
        pie.height = 185
        pie.data = [value for _, value in valid]
        pie.labels = ["" for _ in valid]
        pie.startAngle = 90
        pie.direction = "clockwise"
        pie.slices.strokeWidth = 0.7
        pie.slices.strokeColor = self.WHITE

        palette = [
            self.BLUE,
            self.TEAL,
            self.PURPLE,
            self.CYAN,
            self.AMBER,
            self.GREEN,
            self.RED,
            colors.HexColor("#64748B"),
        ]

        for index in range(len(valid)):
            pie.slices[index].fillColor = palette[index % len(palette)]

        drawing.add(pie)

        total = sum(value for _, value in valid)
        legend_x = 225
        legend_y = height - 30

        for index, (name, value) in enumerate(valid):
            y = legend_y - index * 23
            color = palette[index % len(palette)]
            percentage = value / total * 100 if total else 0

            drawing.add(Rect(
                legend_x,
                y - 2,
                10,
                10,
                fillColor=color,
                strokeColor=None,
            ))
            drawing.add(String(
                legend_x + 17,
                y,
                f"{name}: {value:g} files ({percentage:.1f}%)",
                fontName="Helvetica",
                fontSize=8,
                fillColor=self.TEXT,
            ))

        return drawing

    def _draw_page(self, canvas, doc):
        """Add a consistent header, footer, and page number."""
        canvas.saveState()

        page_width, page_height = A4

        if doc.page > 1:
            canvas.setStrokeColor(self.BORDER)
            canvas.setLineWidth(0.6)
            canvas.line(
                doc.leftMargin,
                page_height - 0.42 * inch,
                page_width - doc.rightMargin,
                page_height - 0.42 * inch,
            )

            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColor(self.NAVY)
            canvas.drawString(
                doc.leftMargin,
                page_height - 0.32 * inch,
                "GITHUB REPOSITORY ANALYZER",
            )

        canvas.setStrokeColor(self.BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(
            doc.leftMargin,
            0.42 * inch,
            page_width - doc.rightMargin,
            0.42 * inch,
        )

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(self.MUTED)
        canvas.drawString(
            doc.leftMargin,
            0.26 * inch,
            "Repository analysis • Generated report",
        )
        canvas.drawRightString(
            page_width - doc.rightMargin,
            0.26 * inch,
            f"Page {doc.page}",
        )

        canvas.restoreState()

    def generate_report(self, repository_info, filename):
        """Create a professional PDF report from repository analysis data."""
        repository_info = self._safe_dict(repository_info)

        output = Path(filename).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        analysis = self._safe_dict(repository_info.get("analysis"))
        summary = self._safe_dict(repository_info.get("ai_summary"))
        recommendations = self._safe_dict(
            repository_info.get("ai_recommendations")
        )
        statistics = self._safe_dict(analysis.get("statistics"))
        languages = self._safe_dict(analysis.get("languages"))

        styles = self._styles()

        doc = SimpleDocTemplate(
            str(output),
            pagesize=A4,
            rightMargin=0.65 * inch,
            leftMargin=0.65 * inch,
            topMargin=0.68 * inch,
            bottomMargin=0.65 * inch,
            title="GitHub Repository Analysis Report",
            author="GitHub Repository Analyzer",
            subject="Repository structure, health signals, and AI insights",
        )

        story = []
        repo_name = str(
            repository_info.get("repository_name") or "Unknown Repository"
        )
        branch = str(repository_info.get("default_branch") or "Unavailable")
        generated_at = datetime.now().strftime("%d %B %Y, %I:%M %p")

        # =====================================
        # Cover Page
        # =====================================

        story.append(Spacer(1, 0.55 * inch))

        cover_band = Table(
            [[Paragraph(
                "REPOSITORY INTELLIGENCE",
                ParagraphStyle(
                    "CoverBandText",
                    parent=styles["CoverSubtitleCustom"],
                    fontName="Helvetica-Bold",
                    fontSize=10,
                    textColor=self.WHITE,
                    spaceAfter=0,
                ),
            )]],
            colWidths=[6.1 * inch],
        )
        cover_band.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), self.BLUE),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 11),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ]))
        story.append(cover_band)
        story.append(Spacer(1, 0.45 * inch))

        story.append(Paragraph(
            "GitHub Repository<br/>Analysis Report",
            styles["CoverTitleCustom"],
        ))

        story.append(Paragraph(
            escape(repo_name),
            styles["CoverSubtitleCustom"],
        ))

        story.append(Spacer(1, 0.12 * inch))
        story.append(Paragraph(
            f"Default branch: {escape(branch)}",
            styles["CoverSubtitleCustom"],
        ))
        story.append(Paragraph(
            f"Generated: {escape(generated_at)}",
            styles["SmallCustom"],
        ))

        score, breakdown = self._calculate_health(
            repository_info,
            analysis,
        )

        story.append(Spacer(1, 0.35 * inch))

        cover_metrics = [
            ["BRANCHES", "COMMITS", "CONTRIBUTORS", "HEALTH SCORE"],
            [
                str(repository_info.get("total_branches", 0)),
                str(repository_info.get("total_commits", 0)),
                str(repository_info.get("total_contributors", 0)),
                f"{score}/100",
            ],
        ]

        metrics_table = Table(
            cover_metrics,
            colWidths=[1.525 * inch] * 4,
        )
        metrics_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self.NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), self.WHITE),
            ("BACKGROUND", (0, 1), (-1, 1), self.PALE_BLUE),
            ("TEXTCOLOR", (0, 1), (-1, 1), self.NAVY),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("FONTSIZE", (0, 1), (-1, 1), 16),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.7, self.BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, self.BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(metrics_table)

        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph(
            "This report summarizes repository metadata, detected technologies, "
            "project organization, activity signals, and AI-generated insights.",
            ParagraphStyle(
                "CoverDescription",
                parent=styles["BodyCustom"],
                alignment=TA_CENTER,
                fontSize=10,
                leading=16,
                textColor=self.MUTED,
            ),
        ))

        story.append(PageBreak())

        # =====================================
        # Repository Overview
        # =====================================

        self._section("1. Repository Overview", story, styles)

        overview_rows = [
            ["Metric", "Value"],
            ["Repository", repo_name],
            ["Default branch", branch],
            ["Branches", repository_info.get("total_branches", 0)],
            ["Commits", repository_info.get("total_commits", 0)],
            ["Contributors", repository_info.get("total_contributors", 0)],
            ["Total files", statistics.get("total_files", 0)],
            ["Directories", statistics.get("total_directories", 0)],
        ]

        story.append(self._table(
            overview_rows,
            [2.2 * inch, 4.0 * inch],
            styles,
        ))

        # =====================================
        # Health Summary and Chart
        # =====================================

        self._section("2. Repository Health", story, styles)

        score_color = (
            self.GREEN if score >= 80
            else self.AMBER if score >= 50
            else self.RED
        )

        health_card = Table(
            [[
                Paragraph(
                    f"{score}<font size='12'> / 100</font>",
                    ParagraphStyle(
                        "HealthCardScore",
                        parent=styles["ScoreCustom"],
                        textColor=score_color,
                    ),
                ),
                Paragraph(
                    escape(self._health_label(score)),
                    styles["BodyCustom"],
                ),
            ]],
            colWidths=[2.0 * inch, 4.2 * inch],
        )
        health_card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), self.PALE_BLUE),
            ("BACKGROUND", (1, 0), (1, 0), self.LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.6, self.BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        story.append(health_card)
        story.append(Spacer(1, 8))
        story.append(self._health_chart(breakdown))
        story.append(Spacer(1, 5))
        story.append(self._paragraph(
            "Interpretation: this score is a heuristic based on available "
            "repository signals. Detected test files do not prove tests pass, "
            "and commit or contributor counts do not establish code quality. "
            "It is not a security audit.",
            styles,
            "SmallCustom",
        ))

        # =====================================
        # Programming Languages
        # =====================================

        self._section("3. Programming Languages", story, styles)

        pie_chart = self._language_pie_chart(languages)
        if pie_chart is not None:
            story.append(pie_chart)
            story.append(Spacer(1, 8))

            valid_languages = []
            for language, count in languages.items():
                try:
                    numeric_count = float(count)
                except (TypeError, ValueError, OverflowError):
                    continue
                if numeric_count > 0:
                    valid_languages.append((str(language), numeric_count))

            valid_languages.sort(key=lambda item: item[1], reverse=True)
            total = sum(count for _, count in valid_languages)

            language_rows = [["Language", "Files", "Share"]]
            for language, count in valid_languages:
                share = f"{count / total * 100:.1f}%" if total else "0%"
                language_rows.append([language, f"{count:g}", share])

            story.append(self._table(
                language_rows,
                [2.8 * inch, 1.6 * inch, 1.8 * inch],
                styles,
            ))
        else:
            story.append(self._paragraph(
                "No programming languages were detected.",
                styles,
            ))

        # =====================================
        # Dependencies
        # =====================================

        self._section("4. Dependencies", story, styles)
        self._bullet_list(
            analysis.get("dependencies"),
            story,
            styles,
            "No dependencies were detected.",
        )

        # =====================================
        # Documentation and Configuration
        # =====================================

        self._section("5. Documentation", story, styles)
        docs = self._safe_list(analysis.get("documentation"))
        docs_display = [
            item.get("path", item.get("name", str(item)))
            if isinstance(item, dict)
            else str(item)
            for item in docs
        ]
        self._bullet_list(
            docs_display,
            story,
            styles,
            "No documentation files were detected.",
        )

        self._section("6. Configuration Files", story, styles)
        configs = self._safe_list(analysis.get("configuration_files"))
        configs_display = [
            item.get("path", item.get("name", str(item)))
            if isinstance(item, dict)
            else str(item)
            for item in configs
        ]
        self._bullet_list(
            configs_display,
            story,
            styles,
            "No configuration files were detected.",
        )

        # =====================================
        # Repository Structure
        # =====================================

        self._section("7. Repository Structure", story, styles)
        structure = self._safe_dict(analysis.get("structure"))

        folders = self._safe_list(
            structure.get("folders")
            or structure.get("directories")
            or structure.get("top_level_folders")
        )
        files = self._safe_list(
            structure.get("files")
            or structure.get("top_level_files")
        )

        story.append(Paragraph("Top-level folders", styles["SubheadingCustom"]))
        self._bullet_list(
            folders,
            story,
            styles,
            "No folder structure was provided.",
        )

        story.append(Paragraph("Top-level files", styles["SubheadingCustom"]))
        self._bullet_list(
            files,
            story,
            styles,
            "No top-level files were provided.",
        )

        # =====================================
        # Hotspot Files
        # =====================================

        self._section("8. Hotspot Files", story, styles)

        hotspots = self._safe_list(analysis.get("hotspot_files"))
        hotspot_rows = [["File", "Changes / commits"]]

        for item in hotspots:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                hotspot_rows.append([str(item[0]), str(item[1])])
            elif isinstance(item, dict):
                hotspot_rows.append([
                    str(item.get("file", item.get("name", "Unknown"))),
                    str(item.get("changes", item.get("commits", 0))),
                ])
            else:
                hotspot_rows.append([str(item), "Unavailable"])

        if len(hotspot_rows) > 1:
            story.append(self._table(
                hotspot_rows,
                [4.7 * inch, 1.5 * inch],
                styles,
            ))
        else:
            story.append(self._paragraph(
                "No hotspot files were detected.",
                styles,
            ))

        # =====================================
        # AI Summary
        # =====================================

        self._section("9. AI Summary", story, styles)

        summary_sections = [
            ("repository_purpose", "Repository purpose"),
            ("technologies_used", "Technologies used"),
            ("project_organization", "Project organization"),
            ("intended_users", "Intended users"),
            ("beginner_summary", "Beginner summary"),
        ]

        for key, heading in summary_sections:
            block = [Paragraph(
                escape(heading),
                styles["SubheadingCustom"],
            )]

            value = summary.get(key, "Unavailable")
            if isinstance(value, (list, tuple)):
                if value:
                    for item in value:
                        block.append(Paragraph(
                            "• " + escape(self._plain_text(item)),
                            styles["BodyCustom"],
                        ))
                else:
                    block.append(self._paragraph(
                        "No information available.",
                        styles,
                        "SmallCustom",
                    ))
            else:
                block.append(self._paragraph(value, styles))

            story.append(KeepTogether(block))

        # =====================================
        # AI Recommendations
        # =====================================

        self._section("10. AI Recommendations", story, styles)

        recommendation_sections = [
            ("strengths", "Repository strengths"),
            ("areas_for_improvement", "Areas for improvement"),
            ("best_practices", "Best practices"),
        ]

        for key, heading in recommendation_sections:
            story.append(Paragraph(
                escape(heading),
                styles["SubheadingCustom"],
            ))
            self._bullet_list(
                recommendations.get(key),
                story,
                styles,
                "No information available.",
            )

        story.append(Paragraph(
            "Overall quality",
            styles["SubheadingCustom"],
        ))
        story.append(self._paragraph(
            recommendations.get("overall_quality", "Unavailable"),
            styles,
        ))

        # =====================================
        # README Excerpt
        # =====================================

        self._section("11. README Excerpt", story, styles)

        readme = analysis.get("readme") or repository_info.get("readme") or ""
        if isinstance(readme, dict):
            readme = self._plain_text(readme)

        readme = str(readme).strip()
        if readme:
            excerpt = readme[:5000]
            if len(readme) > 5000:
                excerpt += "\n\n[Excerpt shortened for report readability.]"

            story.append(self._paragraph(excerpt, styles))
        else:
            story.append(self._paragraph(
                "README content was not available.",
                styles,
            ))

        # =====================================
        # Report Disclaimer
        # =====================================

        story.append(Spacer(1, 12))
        disclaimer = Table(
            [[self._paragraph(
                "Report note: Findings depend on the repository metadata "
                "available at analysis time. AI-generated summaries and "
                "recommendations may require human review. The health score "
                "is an indicative heuristic, not a certification, security "
                "assessment, or substitute for code review and testing.",
                styles,
                "SmallCustom",
            )]],
            colWidths=[6.2 * inch],
        )
        disclaimer.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), self.PALE_BLUE),
            ("BOX", (0, 0), (-1, -1), 0.6, self.BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(disclaimer)

        doc.build(
            story,
            onFirstPage=self._draw_page,
            onLaterPages=self._draw_page,
        )

        return str(output)