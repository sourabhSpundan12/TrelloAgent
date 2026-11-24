import asyncio
from datetime import datetime, timezone, timedelta
import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.mcp_server import trello_tools
from app.models.task_assignment import PerformanceLevel, TaskAssignmentStatus
from app.services.board_service import get_active_board_id
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


# =========================================================================
# Pure-Python Robust PDF 1.4 Builder (Standard Library only)
# =========================================================================

class SimplePDFBuilder:
    """
    Lightweight, deterministic PDF 1.4 document generator written in pure Python.
    Produces strictly valid PDF bytes with Helvetica typography, tables, banners, and badges.
    """

    def __init__(self, title: str = "PM Hooks Report", page_width: float = 595.28, page_height: float = 841.89):
        self.title = title
        self.width = page_width
        self.height = page_height
        self.margin_x = 40.0
        self.margin_top = 40.0
        self.margin_bottom = 45.0
        self.content_width = self.width - (self.margin_x * 2)

        self.pages: List[str] = []
        self.current_stream: List[str] = []
        self.cursor_y = self.height - self.margin_top
        self.page_number = 0
        self._new_page()

    def _new_page(self):
        if self.current_stream:
            self.pages.append("".join(self.current_stream))
            self.current_stream = []
        self.page_number += 1
        self.cursor_y = self.height - self.margin_top
        # Page background
        self.rect(0, 0, self.width, self.height, fill_rgb=(0.985, 0.99, 1.0))

    def check_space(self, needed_height: float) -> bool:
        """Page break automatically if content exceeds printable height."""
        if self.cursor_y - needed_height < self.margin_bottom:
            self._new_page()
            return True
        return False

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill_rgb: Optional[Tuple[float, float, float]] = None,
        stroke_rgb: Optional[Tuple[float, float, float]] = None,
        stroke_width: float = 1.0,
    ):
        cmds = []
        if fill_rgb:
            cmds.append(f"{fill_rgb[0]:.3f} {fill_rgb[1]:.3f} {fill_rgb[2]:.3f} rg\n")
        if stroke_rgb:
            cmds.append(f"{stroke_rgb[0]:.3f} {stroke_rgb[1]:.3f} {stroke_rgb[2]:.3f} RG {stroke_width:.2f} w\n")

        cmds.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re ")
        if fill_rgb and stroke_rgb:
            cmds.append("b\n")
        elif fill_rgb:
            cmds.append("f\n")
        elif stroke_rgb:
            cmds.append("s\n")
        else:
            cmds.append("n\n")
        self.current_stream.append("".join(cmds))

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        rgb: Tuple[float, float, float] = (0.8, 0.85, 0.9),
        width: float = 1.0,
    ):
        self.current_stream.append(
            f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} RG {width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l s\n"
        )

    def text(
        self,
        x: float,
        y: float,
        string: str,
        font: str = "F1",
        size: float = 10.0,
        rgb: Tuple[float, float, float] = (0.1, 0.15, 0.2),
    ):
        clean = (
            str(string)
            .replace("\u2014", "-")
            .replace("\u2013", "-")
            .replace("—", "-")
            .replace("–", "-")
            .replace("’", "'")
            .replace("‘", "'")
            .replace("“", '"')
            .replace("”", '"')
            .replace("•", "*")
            .replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .encode("latin-1", "replace")
            .decode("latin-1")
        )
        self.current_stream.append(
            f"BT /{font} {size:.2f} Tf {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg 1 0 0 1 {x:.2f} {y:.2f} Tm ({clean}) Tj ET\n"
        )

    def draw_header_banner(self, title: str, subtitle: str, badge_text: str):
        banner_h = 56.0
        self.rect(
            self.margin_x,
            self.cursor_y - banner_h,
            self.content_width,
            banner_h,
            fill_rgb=(0.06, 0.09, 0.16),
            stroke_rgb=(0.15, 0.39, 0.92),
            stroke_width=1.5,
        )

        # Title
        self.text(
            self.margin_x + 16,
            self.cursor_y - 24,
            title,
            font="F2",
            size=15,
            rgb=(1.0, 1.0, 1.0),
        )
        # Subtitle
        self.text(
            self.margin_x + 16,
            self.cursor_y - 42,
            subtitle,
            font="F1",
            size=9,
            rgb=(0.7, 0.75, 0.85),
        )

        # Badge pill
        badge_w = max(80.0, len(badge_text) * 6.5)
        badge_x = self.margin_x + self.content_width - badge_w - 14
        self.rect(
            badge_x,
            self.cursor_y - 36,
            badge_w,
            18,
            fill_rgb=(0.15, 0.39, 0.92),
        )
        self.text(
            badge_x + 8,
            self.cursor_y - 32,
            badge_text,
            font="F2",
            size=8.5,
            rgb=(1.0, 1.0, 1.0),
        )

        self.cursor_y -= banner_h + 16

    def draw_section_heading(self, heading: str):
        self.check_space(34)
        h_y = self.cursor_y - 18
        # Accent bar
        self.rect(self.margin_x, h_y - 2, 4, 14, fill_rgb=(0.15, 0.39, 0.92))
        self.text(self.margin_x + 10, h_y, heading.upper(), font="F2", size=10.5, rgb=(0.1, 0.15, 0.25))
        self.line(self.margin_x, h_y - 8, self.margin_x + self.content_width, h_y - 8, rgb=(0.85, 0.88, 0.92), width=1)
        self.cursor_y = h_y - 18

    def draw_metric_cards(self, metrics: List[Dict[str, Any]]):
        """Draws equal metric stat boxes side-by-side."""
        self.check_space(60)
        n = len(metrics)
        gap = 8.0 if n >= 5 else 10.0
        card_w = (self.content_width - ((n - 1) * gap)) / n
        card_h = 50.0

        label_size = 6.8 if n >= 5 else 7.5
        val_size = 13.0 if n >= 5 else 14.0
        sub_size = 5.8 if n >= 5 else 6.5
        pad_x = 7.0 if n >= 5 else 10.0

        for idx, m in enumerate(metrics):
            cx = self.margin_x + idx * (card_w + gap)
            cy = self.cursor_y - card_h

            bg = m.get("bg_rgb", (1.0, 1.0, 1.0))
            border = m.get("border_rgb", (0.85, 0.88, 0.92))
            val_rgb = m.get("val_rgb", (0.06, 0.09, 0.16))

            self.rect(cx, cy, card_w, card_h, fill_rgb=bg, stroke_rgb=border, stroke_width=1)
            # Label
            label_text = m.get("label", "").upper()
            max_label_chars = max(8, int(card_w / (label_size * 0.55)))
            if len(label_text) > max_label_chars:
                label_text = label_text[: max_label_chars - 1] + "."
            self.text(cx + pad_x, cy + 33, label_text, font="F2", size=label_size, rgb=(0.4, 0.45, 0.55))
            # Value
            val_text = str(m.get("value", ""))
            self.text(cx + pad_x, cy + 15, val_text, font="F2", size=val_size, rgb=val_rgb)
            # Subtitle
            if m.get("sub"):
                sub_text = str(m.get("sub", ""))
                max_sub_chars = max(8, int(card_w / (sub_size * 0.55)))
                if len(sub_text) > max_sub_chars:
                    sub_text = sub_text[: max_sub_chars - 1] + "."
                self.text(cx + pad_x, cy + 5, sub_text, font="F1", size=sub_size, rgb=(0.55, 0.6, 0.7))

        self.cursor_y -= card_h + 16

    def draw_table(
        self,
        headers: List[str],
        rows: List[List[str]],
        col_widths: List[float],
        aligns: Optional[List[str]] = None,
    ):
        """Draws a clean striped data table with strictly bounded columns and repeating headers across page breaks."""
        row_h = 19.0
        self.check_space(row_h * 2 + 10)

        def _draw_hdr():
            hy = self.cursor_y - row_h
            self.rect(self.margin_x, hy, self.content_width, row_h, fill_rgb=(0.92, 0.94, 0.97), stroke_rgb=(0.80, 0.84, 0.90))
            cur_x = self.margin_x
            for idx, h in enumerate(headers):
                w = col_widths[idx]
                clean_h = str(h).strip().upper()
                max_h_chars = max(4, int(w / 4.5))
                if len(clean_h) > max_h_chars:
                    clean_h = clean_h[: max_h_chars - 2] + ".."
                self.text(cur_x + 4, hy + 5.5, clean_h, font="F2", size=6.2, rgb=(0.18, 0.23, 0.32))
                cur_x += w
            self.cursor_y = hy

        _draw_hdr()

        # Data rows
        for r_idx, row in enumerate(rows):
            did_break = self.check_space(row_h + 4)
            if did_break:
                _draw_hdr()
            ry = self.cursor_y - row_h
            bg = (1.0, 1.0, 1.0) if r_idx % 2 == 0 else (0.975, 0.985, 0.995)
            self.rect(self.margin_x, ry, self.content_width, row_h, fill_rgb=bg, stroke_rgb=(0.88, 0.91, 0.94), stroke_width=0.7)

            cur_x = self.margin_x
            for c_idx, cell in enumerate(row):
                w = col_widths[c_idx]
                clean_cell = str(cell).strip() if (cell is not None and str(cell).strip() != "") else "-"
                max_chars = max(4, int(w / 4.5))
                if len(clean_cell) > max_chars:
                    clean_cell = clean_cell[: max_chars - 2] + ".."
                self.text(cur_x + 4, ry + 5.5, clean_cell, font="F1", size=6.5, rgb=(0.15, 0.2, 0.28))
                cur_x += w

            self.cursor_y = ry

        self.cursor_y -= 14

    def draw_consolidated_feedback_report(
        self,
        given_by: str,
        feedback_date: str,
        related_task: str,
        category: str,
        follow_up_date: str,
        strengths: List[str],
        improvement_areas: List[str],
        action_items: List[str],
        explicit_hours_statement: str,
    ):
        """Draws formatted Section 4 Feedback Report with metadata, strengths, improvement areas, action items, and hours comparison."""
        box_padding = 12.0
        needed_h = (
            52  # Header + metadata
            + 20 + (len(strengths) * 14)
            + 18 + (len(improvement_areas) * 14)
            + 18 + (len(action_items) * 14)
            + 42 # Multi-line hours statement
            + 20
        )
        self.check_space(needed_h)

        box_y = self.cursor_y - needed_h
        self.rect(
            self.margin_x,
            box_y,
            self.content_width,
            needed_h,
            fill_rgb=(0.995, 1.0, 0.995),
            stroke_rgb=(0.06, 0.72, 0.51),
            stroke_width=1.2,
        )

        inner_y = self.cursor_y - 18
        # Header banner
        self.text(self.margin_x + box_padding, inner_y, "PROJECT MANAGER WEEKLY ASSESSMENT & FEEDBACK", font="F2", size=9.5, rgb=(0.04, 0.45, 0.32))
        inner_y -= 15

        clean_given_by = "Project Manager" if not given_by or "admin" in given_by.lower() else given_by

        # Metadata grid row 1: Given By & Feedback Date
        self.text(self.margin_x + box_padding, inner_y, "FEEDBACK GIVEN BY:", font="F2", size=7.2, rgb=(0.4, 0.45, 0.55))
        self.text(self.margin_x + box_padding + 100, inner_y, clean_given_by, font="F1", size=7.2, rgb=(0.1, 0.15, 0.25))

        self.text(self.margin_x + 310, inner_y, "FEEDBACK DATE:", font="F2", size=7.2, rgb=(0.4, 0.45, 0.55))
        self.text(self.margin_x + 395, inner_y, feedback_date, font="F1", size=7.2, rgb=(0.1, 0.15, 0.25))
        inner_y -= 13

        # Metadata grid row 2: Related Task & Category & Follow-up Date
        self.text(self.margin_x + box_padding, inner_y, "RELATED TASK:", font="F2", size=7.2, rgb=(0.4, 0.45, 0.55))
        clean_rel = related_task if len(related_task) <= 34 else related_task[:31] + "..."
        self.text(self.margin_x + box_padding + 100, inner_y, clean_rel, font="F1", size=7.2, rgb=(0.1, 0.15, 0.25))

        self.text(self.margin_x + 310, inner_y, "CATEGORY:", font="F2", size=7.2, rgb=(0.4, 0.45, 0.55))
        self.text(self.margin_x + 395, inner_y, category, font="F1", size=7.2, rgb=(0.1, 0.15, 0.25))
        inner_y -= 13

        self.text(self.margin_x + box_padding, inner_y, "FOLLOW-UP DATE:", font="F2", size=7.2, rgb=(0.4, 0.45, 0.55))
        self.text(self.margin_x + box_padding + 100, inner_y, follow_up_date, font="F1", size=7.2, rgb=(0.15, 0.35, 0.85))
        inner_y -= 15

        # Divider line
        self.line(self.margin_x + box_padding, inner_y + 4, self.margin_x + self.content_width - box_padding, inner_y + 4, rgb=(0.85, 0.9, 0.88), width=0.8)
        inner_y -= 5

        # 1. Strengths
        self.text(self.margin_x + box_padding, inner_y, "Key Strengths & Notable Highlights:", font="F2", size=8.0, rgb=(0.06, 0.52, 0.35))
        inner_y -= 13
        for s in strengths:
            self.text(self.margin_x + box_padding + 10, inner_y, f"*  {s}", font="F1", size=7.2, rgb=(0.1, 0.25, 0.15))
            inner_y -= 13

        # 2. Improvement Areas
        inner_y -= 3
        self.text(self.margin_x + box_padding, inner_y, "Areas for Improvement & Guidance:", font="F2", size=8.0, rgb=(0.80, 0.40, 0.05))
        inner_y -= 13
        for f in improvement_areas:
            self.text(self.margin_x + box_padding + 10, inner_y, f"*  {f}", font="F1", size=7.2, rgb=(0.35, 0.2, 0.05))
            inner_y -= 13

        # 3. Action Items
        inner_y -= 3
        self.text(self.margin_x + box_padding, inner_y, "Action Items for Next Week:", font="F2", size=8.0, rgb=(0.15, 0.35, 0.75))
        inner_y -= 13
        for a in action_items:
            self.text(self.margin_x + box_padding + 10, inner_y, f"*  {a}", font="F1", size=7.2, rgb=(0.15, 0.2, 0.35))
            inner_y -= 13

        # 4. Explicit Hours Callout Box (multi-line to prevent right border overflow)
        inner_y -= 4
        callout_h = 32.0
        self.rect(
            self.margin_x + box_padding,
            inner_y - callout_h + 8,
            self.content_width - (box_padding * 2),
            callout_h,
            fill_rgb=(0.94, 0.97, 1.0),
            stroke_rgb=(0.25, 0.5, 0.9),
            stroke_width=1,
        )

        if " and actual time" in explicit_hours_statement:
            parts = explicit_hours_statement.split(" and actual time", 1)
            line1 = parts[0].strip() + ","
            line2 = "and actual time" + parts[1].strip()
        else:
            line1 = explicit_hours_statement
            line2 = ""

        self.text(
            self.margin_x + box_padding + 8,
            inner_y - 4,
            line1,
            font="F2",
            size=7.4,
            rgb=(0.1, 0.25, 0.65),
        )
        if line2:
            self.text(
                self.margin_x + box_padding + 8,
                inner_y - 15,
                line2,
                font="F2",
                size=7.4,
                rgb=(0.1, 0.25, 0.65),
            )

        self.cursor_y = box_y - 16

    def draw_feedback_box(
        self,
        strengths: List[str],
        focus_areas: List[str],
        explicit_hours_statement: str,
    ):
        """Draws formatted AI feedback report with explicit required hours statement."""
        box_padding = 12.0
        # Calculate needed height
        needed_h = 32 + (len(strengths) * 16) + 24 + (len(focus_areas) * 16) + 40
        self.check_space(needed_h)

        box_y = self.cursor_y - needed_h
        self.rect(
            self.margin_x,
            box_y,
            self.content_width,
            needed_h,
            fill_rgb=(0.995, 1.0, 0.995),
            stroke_rgb=(0.06, 0.72, 0.51),
            stroke_width=1.2,
        )

        inner_y = self.cursor_y - 20
        # AI Header
        self.text(self.margin_x + box_padding, inner_y, "AI-GENERATED PERFORMANCE & FOCUS FEEDBACK", font="F2", size=9.5, rgb=(0.04, 0.45, 0.32))
        inner_y -= 18

        # 1. Strengths / Good Points
        self.text(self.margin_x + box_padding, inner_y, "[+] What You Have Done Good (Strengths):", font="F2", size=8.5, rgb=(0.06, 0.55, 0.38))
        inner_y -= 14
        for s in strengths:
            self.text(self.margin_x + box_padding + 12, inner_y, f"*  {s}", font="F1", size=8, rgb=(0.1, 0.25, 0.15))
            inner_y -= 14

        # 2. Focus More / Improvements
        inner_y -= 4
        self.text(self.margin_x + box_padding, inner_y, "[!] What Things You Should Focus More On:", font="F2", size=8.5, rgb=(0.85, 0.45, 0.05))
        inner_y -= 14
        for f in focus_areas:
            self.text(self.margin_x + box_padding + 12, inner_y, f"*  {f}", font="F1", size=8, rgb=(0.35, 0.2, 0.05))
            inner_y -= 14

        # 3. Explicit Hours Statement (Required by User)
        inner_y -= 6
        callout_h = 24.0
        self.rect(
            self.margin_x + box_padding,
            inner_y - callout_h + 8,
            self.content_width - (box_padding * 2),
            callout_h,
            fill_rgb=(0.94, 0.97, 1.0),
            stroke_rgb=(0.25, 0.5, 0.9),
            stroke_width=1,
        )
        self.text(
            self.margin_x + box_padding + 8,
            inner_y - 6,
            explicit_hours_statement,
            font="F2",
            size=8,
            rgb=(0.1, 0.25, 0.65),
        )

        self.cursor_y = box_y - 16

    def draw_footer_and_finish(self) -> bytes:
        total_p = len(self.pages) + 1  # current page still open
        ist_tz = timezone(timedelta(hours=5, minutes=30), name="IST")
        now_str = datetime.now(ist_tz).strftime("%d %b %Y, %I:%M %p IST")

        # Seal current page
        if self.current_stream:
            self.pages.append("".join(self.current_stream))
            self.current_stream = []

        total_pages = len(self.pages)

        # Append footers onto each page stream
        for idx in range(total_pages):
            page_num = idx + 1
            footer_cmds = []
            # Horizontal bottom rule
            footer_cmds.append(
                f"0.850 0.880 0.920 RG 1 w {self.margin_x:.2f} {self.margin_bottom:.2f} m "
                f"{(self.margin_x + self.content_width):.2f} {self.margin_bottom:.2f} l s\n"
            )
            # Left footer note
            footer_cmds.append(
                f"BT /F1 7.5 Tf 0.5 0.55 0.6 rg 1 0 0 1 {self.margin_x:.2f} {(self.margin_bottom - 16):.2f} Tm "
                f"(PM Hooks Enterprise Autonomous Assistant  |  CONFIDENTIAL) Tj ET\n"
            )
            # Right footer page count & timestamp
            r_text = f"Page {page_num} of {total_pages}  |  Generated {now_str}"
            footer_cmds.append(
                f"BT /F1 7.5 Tf 0.5 0.55 0.6 rg 1 0 0 1 {(self.width - self.margin_x - 180):.2f} {(self.margin_bottom - 16):.2f} Tm "
                f"({r_text}) Tj ET\n"
            )
            self.pages[idx] += "".join(footer_cmds)

        # Assemble PDF Objects
        current_id = 3
        font1_id = 3
        font2_id = 4
        current_id = 5

        page_entries = []
        for i in range(total_pages):
            p_id = current_id
            c_id = current_id + 1
            current_id += 2
            page_entries.append((p_id, c_id, self.pages[i]))

        kids_str = " ".join([f"{p[0]} 0 R" for p in page_entries])
        pages_dict = f"<< /Type /Pages /Kids [{kids_str}] /Count {total_pages} >>".encode("utf-8")

        all_objs: Dict[int, bytes] = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: pages_dict,
            font1_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            font2_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        }

        for p_id, c_id, content in page_entries:
            c_bytes = content.encode("latin-1", errors="replace")
            p_dict = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width:.2f} {self.height:.2f}] "
                f"/Resources << /Font << /F1 {font1_id} 0 R /F2 {font2_id} 0 R >> >> "
                f"/Contents {c_id} 0 R >>"
            ).encode("utf-8")
            c_stream = (
                b"<< /Length "
                + str(len(c_bytes)).encode("utf-8")
                + b" >>\nstream\n"
                + c_bytes
                + b"\nendstream"
            )
            all_objs[p_id] = p_dict
            all_objs[c_id] = c_stream

        max_id = max(all_objs.keys())
        out = bytearray()
        out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        offsets = {}
        for obj_id in range(1, max_id + 1):
            if obj_id in all_objs:
                offsets[obj_id] = len(out)
                out.extend(f"{obj_id} 0 obj\n".encode("utf-8"))
                out.extend(all_objs[obj_id])
                out.extend(b"\nendobj\n")

        xref_pos = len(out)
        out.extend(f"xref\n0 {max_id + 1}\n".encode("utf-8"))
        out.extend(b"0000000000 65535 f \n")
        for obj_id in range(1, max_id + 1):
            offset = offsets.get(obj_id, 0)
            out.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))

        out.extend(f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("utf-8"))
        return bytes(out)


def _parse_report_dt(val: Optional[Any], default_dt: Optional[datetime]) -> Optional[datetime]:
    if val is None or val == "":
        return default_dt
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    try:
        s = str(val).strip()
        if len(s) == 10 and "-" in s:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return default_dt


def _format_date_short(val: Optional[Any]) -> str:
    if not val:
        return "-"
    ist_tz = timezone(timedelta(hours=5, minutes=30), name="IST")
    if isinstance(val, datetime):
        dt = val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        return dt.astimezone(ist_tz).strftime("%d %b %Y")
    try:
        s = str(val).strip()
        if len(s) == 10 and "-" in s:
            dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=ist_tz)
            return dt.strftime("%d %b %Y")
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ist_tz).strftime("%d %b %Y")
    except Exception:
        return str(val)[:10]


def _format_duration_delta(td: timedelta) -> str:
    total_seconds = int(td.total_seconds())
    if total_seconds <= 0:
        return "0 hrs"
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    if days > 0:
        return f"{days}d {hours}h" if hours > 0 else f"{days} days"
    return f"{max(1, hours)} hrs"


# =========================================================================
# PDF Report Orchestration Service
# =========================================================================

class PDFReportService:
    """Enterprise report generator for Board-wise and Employee-based Weekly Reports with AI feedback."""

    @classmethod
    async def generate_board_weekly_report(
        cls,
        db: AsyncIOMotorDatabase,
        board_id: Optional[str] = None,
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generates comprehensive Board-wise Weekly PDF report containing:
        1. Weekly Board Summary
        2. Performance Report (no. of cards done, est. hours, actual hours taken on entire week)
        3. Occupancy Report (capacity vs workload, busy vs free team members)
        4. AI Feedback Report with explicit hours comparison statement.
        """
        active_board_id = board_id
        if not active_board_id and db is not None:
            try:
                active_board_id = await get_active_board_id(db, board_id)
            except Exception:
                active_board_id = None

        cards_res, lists_res, members_res = await asyncio.gather(
            trello_tools.trello_list_cards(board_id=active_board_id),
            trello_tools.trello_list_lists(board_id=active_board_id),
            trello_tools.trello_list_board_members(board_id=active_board_id),
        )

        cards = cards_res.get("cards", [])
        lists = lists_res.get("lists", [])
        members = members_res.get("members", [])
        list_map = {l["id"]: l["name"] for l in lists}

        # Date window: Entire past week (7 days)
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        week_str = f"{week_start.strftime('%d %b %Y')} - {now.strftime('%d %b %Y')}"

        # Reconcile completed vs in-progress
        completed_cards = []
        in_progress_cards = []
        overdue_cards = []

        total_cards_done = 0
        total_est_minutes = 0
        total_act_minutes = 0

        # Query MongoDB task assignments to fetch exact logged duration minutes
        assignments_map = {}
        if db is not None:
            try:
                cursor = db["task_assignments"].find()
                async for a in cursor:
                    assignments_map[a.get("task_id")] = a
                    assignments_map[a.get("task_title", "").strip().lower()] = a
            except Exception:
                pass

        table_rows: List[List[str]] = []
        for c in cards:
            c_name = c.get("name", "Untitled")
            lid = c.get("idList")
            lname = list_map.get(lid, "To Do")
            is_done = c.get("dueComplete", False) or any(k in lname.lower() for k in ("done", "complete", "closed"))
            is_prog = any(k in lname.lower() for k in ("doing", "in progress", "progress", "review"))

            # Check due
            due_iso = c.get("due")
            is_overdue = False
            if due_iso and not is_done:
                try:
                    dt = datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if now > dt:
                        is_overdue = True
                except Exception:
                    pass

            # Duration matching
            t_match = assignments_map.get(c.get("id")) or assignments_map.get(c_name.strip().lower())
            est_m = (t_match.get("estimated_duration_minutes") if t_match else None) or 120  # default 2h
            act_m = (t_match.get("actual_duration_minutes") if t_match else None) or (est_m if is_done else 0)

            total_est_minutes += est_m

            if is_done:
                completed_cards.append(c)
                total_cards_done += 1
                total_act_minutes += act_m
            elif is_prog:
                in_progress_cards.append(c)
            elif is_overdue:
                overdue_cards.append(c)

            status_str = "Done" if is_done else ("Overdue" if is_overdue else ("Doing" if is_prog else "To Do"))
            table_rows.append([
                c_name,
                lname,
                f"{est_m / 60.0:.1f}h",
                f"{act_m / 60.0:.1f}h" if is_done else "-",
                status_str,
            ])

        total_est_hours = round(total_est_minutes / 60.0, 1)
        total_act_hours = round(total_act_minutes / 60.0, 1)
        efficiency_pct = round((total_est_hours / max(1.0, total_act_hours)) * 100.0, 1) if total_act_hours > 0 else 100.0

        # Occupancy
        active_members_count = max(1, len(members))
        weekly_team_capacity_hours = active_members_count * 40.0  # standard 40h per employee
        occupancy_pct = min(100.0, round((total_est_hours / weekly_team_capacity_hours) * 100.0, 1))

        # Explicit Statement
        explicit_hours_statement = (
            f"Board Weekly Summary: Total estimated time to complete tasks in entire week was {total_est_hours} hours "
            f"and actual time taken was {total_act_hours} hours."
        )

        strengths = [
            f"Delivered {total_cards_done} task card(s) during the weekly cycle with structured verification.",
            f"Maintained an overall team velocity of {efficiency_pct}% relative to planned milestones.",
            f"Occupancy rate settled at {occupancy_pct}%, indicating stable team bandwidth management.",
        ]

        focus_areas = [
            f"Address {len(overdue_cards)} overdue item(s) to avoid cascading end-of-sprint bottlenecks.",
            f"Align task estimation granularity on items requiring more than 4+ hours of active implementation.",
            "Conduct mid-week standup syncs to reassign blocked cards across free team members.",
        ]

        # Build PDF
        builder = SimplePDFBuilder(title=f"Board Weekly Report - {week_str}")
        builder.draw_header_banner(
            title="PM Hooks - Executive Weekly Board Report",
            subtitle=f"Trello Board: {active_board_id or 'Primary'}  |  Reporting Window: {week_str}",
            badge_text="BOARD REPORT",
        )

        # 1. Weekly Report Metrics
        builder.draw_section_heading("1. Weekly Report & Card Status Breakdown")
        builder.draw_metric_cards([
            {"label": "Total Cards", "value": len(cards), "sub": "Tracked on Board", "bg_rgb": (0.95, 0.97, 1.0)},
            {"label": "Cards Done", "value": total_cards_done, "sub": "Completed This Week", "bg_rgb": (0.94, 0.99, 0.95), "val_rgb": (0.05, 0.6, 0.3)},
            {"label": "In Progress", "value": len(in_progress_cards), "sub": "Currently Active", "bg_rgb": (0.95, 0.97, 1.0), "val_rgb": (0.15, 0.35, 0.85)},
            {"label": "Overdue Cards", "value": len(overdue_cards), "sub": "Past Due Date", "bg_rgb": (1.0, 0.95, 0.95), "val_rgb": (0.85, 0.2, 0.2)},
        ])

        # 2. Performance Report Metrics
        builder.draw_section_heading("2. Weekly Performance & Time Metrics")
        builder.draw_metric_cards([
            {"label": "No. Cards Done", "value": total_cards_done, "sub": "Entire Week Deliverables", "bg_rgb": (0.94, 0.99, 0.95), "val_rgb": (0.05, 0.6, 0.3)},
            {"label": "Total Est. Time", "value": f"{total_est_hours} hrs", "sub": "Entire Week Allocation", "bg_rgb": (0.95, 0.97, 1.0)},
            {"label": "Total Act. Time", "value": f"{total_act_hours} hrs", "sub": "Entire Week Logged", "bg_rgb": (0.98, 0.96, 1.0), "val_rgb": (0.45, 0.2, 0.75)},
            {"label": "Velocity Ratio", "value": f"{efficiency_pct}%", "sub": "Est / Actual Hours", "bg_rgb": (0.95, 0.99, 0.97), "val_rgb": (0.05, 0.6, 0.35)},
        ])

        # 3. Occupancy Report
        builder.draw_section_heading("3. Team Occupancy & Capacity Utilization")
        builder.draw_metric_cards([
            {"label": "Active Members", "value": active_members_count, "sub": "Collaborators", "bg_rgb": (0.95, 0.97, 1.0)},
            {"label": "Team Capacity", "value": f"{int(weekly_team_capacity_hours)} hrs", "sub": "40h / Member Std", "bg_rgb": (0.95, 0.97, 1.0)},
            {"label": "Workload Allocated", "value": f"{total_est_hours} hrs", "sub": "Tasks Planned", "bg_rgb": (0.95, 0.97, 1.0)},
            {"label": "Occupancy Rate", "value": f"{occupancy_pct}%", "sub": "Bandwidth Utilized", "bg_rgb": (0.95, 0.99, 0.95), "val_rgb": (0.05, 0.6, 0.3)},
        ])

        # 4. AI Feedback Report
        builder.draw_section_heading("4. AI Feedback & Strategic Guidance")
        builder.draw_feedback_box(strengths, focus_areas, explicit_hours_statement)

        # 5. Task List Sample Table
        if table_rows:
            builder.draw_section_heading("5. Board Task Deliverables Registry")
            builder.draw_table(
                headers=["Task Card Title", "Trello List", "Est Time", "Act Time", "Status"],
                rows=table_rows[:12],
                col_widths=[230.0, 105.0, 60.0, 60.0, 60.0],
            )

        pdf_bytes = builder.draw_footer_and_finish()

        summary_data = {
            "board_id": active_board_id,
            "week_range": week_str,
            "total_cards": len(cards),
            "cards_done": total_cards_done,
            "total_estimated_hours": total_est_hours,
            "total_actual_hours": total_act_hours,
            "efficiency_percentage": efficiency_pct,
            "occupancy_percentage": occupancy_pct,
            "explicit_hours_statement": explicit_hours_statement,
        }

        return pdf_bytes, summary_data

    @classmethod
    async def generate_employee_weekly_report(
        cls,
        db: AsyncIOMotorDatabase,
        employee_id: str,
        employee_name: Optional[str] = None,
        board_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generates Single Consolidated Employee Weekly Report PDF containing strictly four sections:
        1. Weekly Task Report: Total assigned, completed, pending, in-progress and overdue tasks,
           with a task-wise table containing task name, board, list, assigned date, due date, status,
           completion date and overdue duration.
        2. Performance Report: On-time completion rate, late completed tasks, task completion rate,
           estimated vs actual time and average time per completed task.
        3. Occupancy Report: Total available working hours, estimated task hours, actual hours spent,
           occupancy percentage and available hours.
        4. Feedback Report: Feedback given by, feedback date, related task, category, strengths,
           improvement areas, action items and follow-up date.
        """
        now = datetime.now(timezone.utc)
        start_dt = _parse_report_dt(from_date, now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = _parse_report_dt(to_date, now).replace(hour=23, minute=59, second=59, microsecond=999999)
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        date_range_str = f"{start_dt.strftime('%d %b %Y')} - {end_dt.strftime('%d %b %Y')}"

        # 1. Resolve employee profile from DB
        resolved_name = employee_name
        resolved_email = f"{employee_id}@company.local"
        resolved_role = "Software Engineer"
        resolved_dept = "Engineering"

        if db is not None:
            try:
                from bson import ObjectId
                u = None
                try:
                    u = await db["users"].find_one({"_id": ObjectId(employee_id)})
                except Exception:
                    pass
                if not u:
                    u = await db["users"].find_one({"$or": [{"email": employee_id}, {"full_name": employee_id}]})
                if u:
                    resolved_name = u.get("full_name") or resolved_name
                    resolved_email = u.get("email") or resolved_email
                    resolved_role = u.get("role") or resolved_role
                    resolved_dept = u.get("department") or resolved_dept
            except Exception:
                pass

        if not resolved_name:
            resolved_name = employee_id

        # 2. Query task assignments for this employee
        emp_match: List[Dict[str, Any]] = [
            {"employee_id": str(employee_id)},
            {"employee_name": resolved_name},
            {"employee_email": resolved_email},
        ]
        raw_tasks: List[Dict[str, Any]] = []
        if db is not None:
            try:
                cursor = db["task_assignments"].find({
                    "$or": emp_match,
                    "status": {"$ne": TaskAssignmentStatus.CANCELLED.value},
                })
                raw_tasks = await cursor.to_list(length=300)
            except Exception:
                pass

        # Also pull live cards from Trello to ensure live fidelity
        list_map: Dict[str, str] = {}
        try:
            lists_res = await trello_tools.trello_list_lists(board_id=board_id)
            for l in lists_res.get("lists", []):
                list_map[l.get("id")] = l.get("name")
        except Exception:
            pass

        live_cards_by_id: Dict[str, Dict[str, Any]] = {}
        live_cards_by_name: Dict[str, Dict[str, Any]] = {}
        try:
            cards_res = await trello_tools.trello_list_cards(board_id=board_id)
            for c in cards_res.get("cards", []):
                cid_str = str(c.get("id") or "")
                cname_str = c.get("name", "").strip().lower()
                if cid_str:
                    live_cards_by_id[cid_str] = c
                if cname_str:
                    live_cards_by_name[cname_str] = c

                card_members = c.get("idMembers", [])
                card_name = c.get("name", "")
                is_assigned = (
                    employee_id in card_members
                    or (resolved_name and resolved_name.lower() in card_name.lower())
                    or any(m in [str(employee_id)] for m in card_members)
                )
                if is_assigned:
                    already_in = any(
                        str(t.get("task_id", "")) == cid_str or str(t.get("trello_card_id", "")) == cid_str
                        for t in raw_tasks
                    )
                    if not already_in:
                        raw_tasks.append({
                            "task_id": c.get("id"),
                            "trello_card_id": c.get("id"),
                            "task_title": card_name,
                            "board_id": board_id or "primary_board",
                            "board_name": "Trello Sprint",
                            "list_id": c.get("idList"),
                            "list_name": list_map.get(c.get("idList"), "Sprint Backlog"),
                            "status": "COMPLETED" if c.get("dueComplete") else "IN_PROGRESS",
                            "estimated_duration_minutes": 120,
                            "actual_duration_minutes": 120 if c.get("dueComplete") else 60,
                            "due_date": c.get("due"),
                            "created_at": now - timedelta(days=2),
                            "assigned_at": now - timedelta(days=2),
                        })
        except Exception:
            pass

        # 3. Filter tasks with respect to reporting date range
        filtered_tasks = []
        for t in raw_tasks:
            t_created = _parse_report_dt(t.get("created_at") or t.get("assigned_at"), None)
            t_completed = _parse_report_dt(t.get("completed_at"), None)
            t_due = _parse_report_dt(t.get("due_date"), None)

            in_range = True
            if t_created or t_completed or t_due:
                if t_created and t_created > end_dt:
                    in_range = False
                elif t_completed and t_completed < start_dt:
                    in_range = False
            if in_range:
                filtered_tasks.append(t)

        if not filtered_tasks and raw_tasks:
            # Fallback to all tasks so real data is preserved if bounds are wide
            filtered_tasks = raw_tasks

        # 4. Process each task and build Task Table Rows for Section 1
        table_rows: List[List[str]] = []
        completed_tasks: List[Dict[str, Any]] = []
        in_progress_tasks: List[Dict[str, Any]] = []
        pending_tasks: List[Dict[str, Any]] = []
        overdue_tasks: List[Dict[str, Any]] = []
        late_completed_tasks: List[Dict[str, Any]] = []

        pm_name_from_tasks = None

        for t in filtered_tasks:
            t_name = t.get("task_title") or t.get("name") or "Untitled Task"
            b_name = t.get("board_name") or (t.get("board_id") or "Sprint Board")
            if b_name.lower().startswith("primary trello"):
                b_name = "Primary Board"
            elif len(b_name) > 13:
                b_name = b_name[:11] + ".."
            pm_name_from_tasks = pm_name_from_tasks or t.get("project_manager_name")

            # Match live card for accurate status and list
            c_key = str(t.get("trello_card_id") or t.get("task_id") or "")
            live_c = live_cards_by_id.get(c_key) or live_cards_by_name.get(t_name.strip().lower())

            raw_status = str(t.get("status") or "").lower()
            assigned_raw = t.get("assigned_at") or t.get("created_at")
            due_raw = t.get("due_date") or t.get("due") or (live_c.get("due") if live_c else None)
            comp_raw = t.get("completed_at")

            assigned_str = _format_date_short(assigned_raw)
            due_str = _format_date_short(due_raw)
            comp_str = _format_date_short(comp_raw)

            due_dt = _parse_report_dt(due_raw, None)
            comp_dt = _parse_report_dt(comp_raw, None)

            is_done = (
                raw_status in (TaskAssignmentStatus.COMPLETED.value, "completed", "done", "closed")
                or bool(t.get("dueComplete"))
                or (bool(live_c.get("dueComplete")) if live_c else False)
                or (comp_raw is not None)
            )

            # Accurate list name resolution (ensuring completed cards don't show "To Do")
            live_list_id = live_c.get("idList") if live_c else (t.get("list_id") or t.get("idList"))
            live_list_name = list_map.get(live_list_id) if live_list_id else None
            l_name = live_list_name or t.get("list_name")

            is_overdue = False
            if is_done:
                status_str = "COMPLETED"
                completed_tasks.append(t)
                # For completed tasks, list must accurately reflect completion
                if not l_name or l_name.strip().lower() in ("to do", "todo", "backlog", "sprint backlog", "untitled", "-"):
                    l_name = "Done"
                elif "done" not in l_name.lower() and "complete" not in l_name.lower():
                    l_name = "Done"
            else:
                if due_dt and now > due_dt:
                    is_overdue = True
                    status_str = "OVERDUE"
                    overdue_tasks.append(t)
                elif raw_status in (TaskAssignmentStatus.IN_PROGRESS.value, "in_progress", "doing", "progress", "review"):
                    status_str = "IN_PROGRESS"
                    in_progress_tasks.append(t)
                else:
                    status_str = "PENDING"
                    pending_tasks.append(t)

                if status_str == "IN_PROGRESS" and (not l_name or l_name.strip().lower() in ("to do", "todo")):
                    l_name = "In Progress"
                elif not l_name:
                    l_name = "To Do"

            # Overdue duration calculation
            overdue_duration_str = "None"
            if is_done:
                if due_dt and comp_dt:
                    if comp_dt > due_dt:
                        delta = comp_dt - due_dt
                        overdue_duration_str = _format_duration_delta(delta)
                        late_completed_tasks.append(t)
                    else:
                        overdue_duration_str = "None (On-Time)"
                else:
                    overdue_duration_str = "None"
            elif is_overdue and due_dt and now > due_dt:
                delta = now - due_dt
                overdue_duration_str = _format_duration_delta(delta)

            table_rows.append([
                t_name,
                b_name,
                l_name,
                assigned_str,
                due_str,
                status_str,
                comp_str,
                overdue_duration_str,
            ])

        total_assigned = len(filtered_tasks)
        total_completed = len(completed_tasks)
        total_pending = len(pending_tasks)
        total_in_progress = len(in_progress_tasks)
        total_overdue = len(overdue_tasks)

        # 5. Section 2: Performance Report Metrics
        on_time_count = total_completed - len(late_completed_tasks)
        on_time_rate = round((on_time_count / max(1, total_completed)) * 100.0, 1) if total_completed > 0 else 100.0
        late_completed_count = len(late_completed_tasks)
        task_completion_rate = round((total_completed / max(1, total_assigned)) * 100.0, 1) if total_assigned > 0 else 0.0

        est_mins_list = [t.get("estimated_duration_minutes") or 120 for t in filtered_tasks]
        act_mins_list = [t.get("actual_duration_minutes") or (t.get("estimated_duration_minutes") or 120) for t in completed_tasks]

        total_est_minutes = sum(est_mins_list)
        total_act_minutes = sum(act_mins_list)
        total_est_hours = round(total_est_minutes / 60.0, 1)
        total_act_hours = round(total_act_minutes / 60.0, 1)
        avg_time_per_completed = round(total_act_hours / max(1, total_completed), 1) if total_completed > 0 else 0.0

        # 6. Section 3: Occupancy Report Metrics
        # Organization standard: 5 working days per week, 9 hours per day = 45.0 hrs total capacity
        cur_day = start_dt.date()
        end_day = end_dt.date()
        b_days = 0
        while cur_day <= end_day:
            if cur_day.weekday() < 5:  # Monday to Friday
                b_days += 1
            cur_day += timedelta(days=1)
        if b_days == 0:
            b_days = max(1, (end_day - cur_day).days if (end_day >= cur_day) else 1)

        # Standard weekly sprint is 45.0 hrs (5 days * 9.0 hrs)
        if (end_dt - start_dt).days <= 7 and b_days <= 5:
            total_available_hours = 45.0
        else:
            total_available_hours = float(b_days * 9.0)

        occupancy_percentage = round((total_est_hours / max(1.0, total_available_hours)) * 100.0, 1)
        available_hours = round(max(0.0, total_available_hours - total_est_hours), 1)

        # 7. Section 4: Feedback Report
        feedback_given_by = pm_name_from_tasks or "Project Manager"
        if not feedback_given_by or "admin" in feedback_given_by.lower():
            feedback_given_by = "Project Manager"
        feedback_date = end_dt.strftime("%d %b %Y")
        related_task = completed_tasks[0].get("task_title", "Sprint Deliverables Execution") if completed_tasks else "Weekly Sprint Deliverables & Task Execution"
        feedback_category = "Sprint Velocity & Technical Execution"
        follow_up_date = (end_dt + timedelta(days=7)).strftime("%d %b %Y")

        explicit_hours_statement = (
            f"This is your estimated time to complete the task in entire week: {total_est_hours} hours "
            f"and actual time you have taken to complete the task on entire week: {total_act_hours} hours."
        )

        strengths = [
            f"Good progress on sprint deliverables with {total_completed} task(s) finalized and steady completion momentum.",
            f"Maintained solid focus across assigned cards with {total_act_hours} hours of active technical execution.",
        ]

        focus_areas = [
            f"Address {total_overdue} overdue task(s) and escalate roadblocks early during standups to prevent target slippage." if total_overdue else "Ensure in-progress cards are updated daily on the board to reflect current stage.",
            "Align upfront task estimates closer to actual scope to reduce variance between planned and logged hours.",
        ]

        action_items = [
            "Deconstruct complex tickets exceeding 4 hours into smaller sub-tasks during sprint planning.",
            "Sync with the project manager at mid-week check-in to clear any technical dependencies.",
        ]

        # 8. Assemble PDF Document with Strictly 4 Sections (NO SUMMARY SECTION)
        builder = SimplePDFBuilder(title=f"Consolidated Employee Weekly Report - {resolved_name}")
        builder.draw_header_banner(
            title="PM Hooks - Consolidated Employee Weekly Report",
            subtitle=f"Employee: {resolved_name} ({resolved_email})  |  Reporting Window: {date_range_str}",
            badge_text=resolved_dept.upper(),
        )

        # SECTION 1: WEEKLY TASK REPORT
        builder.draw_section_heading("1. Weekly Task Report")
        builder.draw_metric_cards([
            {"label": "Total Assigned", "value": total_assigned, "sub": "Weekly Tasks", "bg_rgb": (0.95, 0.97, 1.0)},
            {"label": "Completed", "value": total_completed, "sub": "Delivered", "bg_rgb": (0.94, 0.99, 0.95), "val_rgb": (0.05, 0.6, 0.3)},
            {"label": "In-Progress", "value": total_in_progress, "sub": "Currently Active", "bg_rgb": (0.95, 0.97, 1.0), "val_rgb": (0.15, 0.35, 0.85)},
            {"label": "Pending", "value": total_pending, "sub": "Awaiting Pickup", "bg_rgb": (0.98, 0.98, 0.99), "val_rgb": (0.4, 0.45, 0.55)},
            {"label": "Overdue", "value": total_overdue, "sub": "Exceeded Due Date", "bg_rgb": (1.0, 0.95, 0.95), "val_rgb": (0.85, 0.2, 0.2)},
        ])
        builder.draw_table(
            headers=["Task Name", "Board", "List", "Assigned", "Due Date", "Status", "Completion", "Overdue Duration"],
            rows=table_rows if table_rows else [["No task assignments recorded in this date range", "-", "-", "-", "-", "-", "-", "-"]],
            col_widths=[100.0, 60.0, 48.0, 62.0, 62.0, 58.0, 65.0, 85.0],
        )

        # SECTION 2: PERFORMANCE REPORT
        builder.draw_section_heading("2. Performance Report")
        builder.draw_metric_cards([
            {"label": "On-Time Rate", "value": f"{on_time_rate}%", "sub": "SLA Compliance", "bg_rgb": (0.95, 0.99, 0.97), "val_rgb": (0.05, 0.6, 0.35)},
            {"label": "Late Completed", "value": late_completed_count, "sub": "Past Due Deliveries", "bg_rgb": (1.0, 0.97, 0.94), "val_rgb": (0.8, 0.45, 0.05)},
            {"label": "Task Completion", "value": f"{task_completion_rate}%", "sub": f"{total_completed}/{total_assigned} Assigned", "bg_rgb": (0.95, 0.97, 1.0), "val_rgb": (0.15, 0.35, 0.85)},
            {"label": "Estimated Time", "value": f"{total_est_hours} hrs", "sub": "Total Planned", "bg_rgb": (0.95, 0.97, 1.0), "val_rgb": (0.15, 0.35, 0.85)},
            {"label": "Actual Time", "value": f"{total_act_hours} hrs", "sub": "Total Logged", "bg_rgb": (0.98, 0.96, 1.0), "val_rgb": (0.45, 0.2, 0.75)},
        ])

        # SECTION 3: OCCUPANCY REPORT
        builder.draw_section_heading("3. Occupancy Report")
        builder.draw_metric_cards([
            {"label": "Total Capacity", "value": f"{total_available_hours} hrs", "sub": "45 hrs (5d x 9h)", "bg_rgb": (0.95, 0.97, 1.0)},
            {"label": "Estimated Hours", "value": f"{total_est_hours} hrs", "sub": "Estimated Task Hours", "bg_rgb": (0.95, 0.97, 1.0)},
            {"label": "Actual Hours", "value": f"{total_act_hours} hrs", "sub": "Actual Hours Spent", "bg_rgb": (0.98, 0.96, 1.0), "val_rgb": (0.45, 0.2, 0.75)},
            {"label": "Occupancy Rate", "value": f"{occupancy_percentage}%", "sub": "Occupancy Percentage", "bg_rgb": (0.94, 0.99, 0.95), "val_rgb": (0.05, 0.6, 0.3)},
            {"label": "Available Hours", "value": f"{available_hours} hrs", "sub": "Available Hours Remaining", "bg_rgb": (0.95, 0.97, 1.0)},
        ])

        # SECTION 4: FEEDBACK REPORT
        builder.draw_section_heading("4. Feedback Report")
        builder.draw_consolidated_feedback_report(
            given_by=feedback_given_by,
            feedback_date=feedback_date,
            related_task=related_task,
            category=feedback_category,
            follow_up_date=follow_up_date,
            strengths=strengths,
            improvement_areas=focus_areas,
            action_items=action_items,
            explicit_hours_statement=explicit_hours_statement,
        )

        pdf_bytes = builder.draw_footer_and_finish()

        summary_data = {
            "employee_id": employee_id,
            "employee_name": resolved_name,
            "employee_email": resolved_email,
            "week_range": date_range_str,
            "cards_done": total_completed,
            "total_assigned": total_assigned,
            "completed_tasks": total_completed,
            "pending_tasks": total_pending,
            "in_progress_tasks": total_in_progress,
            "overdue_tasks": total_overdue,
            "on_time_rate": on_time_rate,
            "late_completed_tasks": late_completed_count,
            "task_completion_rate": task_completion_rate,
            "total_estimated_hours": total_est_hours,
            "total_actual_hours": total_act_hours,
            "avg_time_per_completed_task": avg_time_per_completed,
            "total_available_hours": total_available_hours,
            "occupancy_percentage": occupancy_percentage,
            "available_hours": available_hours,
            "explicit_hours_statement": explicit_hours_statement,
        }

        return pdf_bytes, summary_data

    @classmethod
    async def send_report_to_admin(
        cls,
        to_email: str,
        report_type: str,  # "Board Weekly Report" or "Employee Weekly Report"
        pdf_bytes: bytes,
        filename: str,
        summary_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Sends the generated PDF report attached to an enterprise HTML email directly to the admin."""
        email_service = EmailService()
        subject = f"PM Hooks Executive Report: {report_type} ({summary_data.get('week_range', 'Weekly')})"

        cards_done = summary_data.get("cards_done", 0)
        est_h = summary_data.get("total_estimated_hours", 0.0)
        act_h = summary_data.get("total_actual_hours", 0.0)
        explicit_statement = summary_data.get("explicit_hours_statement", "")

        text_content = f"""PM Hooks Executive Report: {report_type}
Week: {summary_data.get('week_range')}

Summary Metrics:
- Cards Done: {cards_done}
- Total Estimated Time: {est_h} hours
- Total Actual Time Taken: {act_h} hours
- Statement: {explicit_statement}

Please find the complete official PDF report attached to this email.
"""

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{report_type}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0b0f19; margin: 0; padding: 24px; color: #f8fafc; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #111827; border: 1px solid #1f2937; border-radius: 16px; padding: 32px 24px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); }}
    .header {{ border-bottom: 1px solid #1f2937; padding-bottom: 16px; margin-bottom: 20px; }}
    .title {{ font-size: 18px; font-weight: 700; color: #38bdf8; margin: 0 0 4px 0; }}
    .subtitle {{ font-size: 12px; color: #94a3b8; margin: 0; }}
    .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }}
    .stat-card {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; padding: 14px; }}
    .stat-label {{ font-size: 10px; color: #64748b; font-weight: 600; text-transform: uppercase; margin-bottom: 4px; }}
    .stat-value {{ font-size: 20px; font-weight: 800; color: #f1f5f9; }}
    .callout {{ background: rgba(56, 189, 248, 0.08); border-left: 4px solid #0284c7; border-radius: 8px; padding: 14px; margin-bottom: 24px; font-size: 13px; color: #bae6fd; line-height: 1.5; }}
    .footer {{ font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #1f2937; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2 class="title">{report_type}</h2>
      <p class="subtitle">Reporting Period: {summary_data.get('week_range', 'Current Sprint')}</p>
    </div>

    <div class="callout">
      <strong>AI Report Summary:</strong><br/>
      {explicit_statement}
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Cards Completed</div>
        <div class="stat-value">{cards_done}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Estimated Time</div>
        <div class="stat-value">{est_h} hrs</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Actual Time Taken</div>
        <div class="stat-value">{act_h} hrs</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Occupancy Rate</div>
        <div class="stat-value">{summary_data.get('occupancy_percentage', 0)}%</div>
      </div>
    </div>

    <p style="font-size: 12px; color: #cbd5e1; margin-bottom: 20px;">
      Attached is the official <strong>{filename}</strong> document covering the Weekly Report, Performance breakdown, Occupancy metrics, and AI Feedback.
    </p>

    <div class="footer">
      PM Hooks Autonomous Enterprise Assistant &bull; Generated automatically for Administrator
    </div>
  </div>
</body>
</html>"""

        await email_service.send_report_pdf_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            pdf_bytes=pdf_bytes,
            filename=filename,
        )

        return {
            "status": "SUCCESS",
            "message": f"Report successfully delivered to admin email {to_email}",
            "recipient": to_email,
            "filename": filename,
            "summary": summary_data,
        }

