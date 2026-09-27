#!/usr/bin/env python3.12
"""build_deck.py — render the hackathon submission deck PDF from its markdown source.

Usage:
    python3.12 scripts/build_deck.py [source.md] [out.pdf]
    # defaults: deliverables/deck/postmortem-generator-deck-v1.md -> postmortem-generator-deck-v1.pdf

The markdown source is canonical (see the grammar comment inside it). This script
only renders: slides split on `---`, `#` titles, `##` subtitle (title slide),
`- ` bullets, pipe tables, `::kicker …::` / `::layout …::` directives, and the
inline styles **bold**, *italic*, `code`, plus badge emoji (🟢🟡🔴 -> colored dots).
Anything else in the source raises, so source and PDF cannot silently diverge.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

REPO = Path(__file__).resolve().parent.parent
SRC_DEFAULT = REPO / "deliverables/deck/postmortem-generator-deck-v1.md"
OUT_DEFAULT = REPO / "deliverables/deck/postmortem-generator-deck-v1.pdf"

# --- theme (sober, light, one accent) ----------------------------------------
PAGE_W, PAGE_H = 338.667, 190.5  # mm, 16:9
MARGIN = 20.0
INK = (22, 33, 58)        # dark navy
MUTED = (90, 100, 120)
ACCENT = (15, 98, 254)    # IBM blue
HAIRLINE = (213, 218, 227)
PANEL = (245, 247, 250)
HEADER_BG = (238, 241, 246)
BOB_FILL = (232, 240, 255)
GREEN = (31, 138, 76)
AMBER = (181, 138, 0)
RED = (197, 34, 31)

BADGE = {"🟢": (GREEN, "●"), "🟡": (AMBER, "●"), "🔴": (RED, "●")}
TICK = {"✓": GREEN, "✗": RED}

FONTS = {
    ("DejaVu", ""): "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ("DejaVu", "B"): "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ("DejaVu", "I"): "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    ("DejaVu", "BI"): "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    ("DejaVuMono", ""): "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ("DejaVuMono", "B"): "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
}

INLINE_RE = re.compile(r"(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)")

Run = dict  # {text, bold, italic, mono, color}

# --- markdown parsing ---------------------------------------------------------


def parse_slides(text: str) -> list[dict]:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)  # strip HTML comments
    slides: list[dict] = []
    for chunk in text.split("\n---\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        slide = {"title": "", "subtitle": "", "kicker": "", "layout": "standard",
                 "bullets": [], "table": None, "post_bullets": []}
        table: list[list[str]] = []
        for raw in chunk.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("# ") and not slide["title"]:
                slide["title"] = line[2:].strip()
            elif line.startswith("## ") and not slide["subtitle"]:
                slide["subtitle"] = line[3:].strip()
            elif (m := re.fullmatch(r"::(\w+)\s+(.+)::", line)):
                key, val = m.group(1), m.group(2).strip()
                if key == "kicker":
                    slide["kicker"] = val
                elif key == "layout":
                    slide["layout"] = val
                else:
                    raise ValueError(f"unknown directive ::{key}:: in slide {slide['title']!r}")
            elif line.startswith("- "):
                (slide["post_bullets"] if table else slide["bullets"]).append(line[2:].strip())
            elif line.startswith("|"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    continue  # separator row
                table.append(cells)
            else:
                raise ValueError(f"unparseable line in slide {slide['title']!r}: {line!r}")
        if table:
            if len(set(len(r) for r in table)) != 1:
                raise ValueError(f"ragged table in slide {slide['title']!r}")
            slide["table"] = table
        if not slide["title"]:
            raise ValueError(f"slide missing title: {chunk[:60]!r}")
        slides.append(slide)
    return slides


# --- inline runs ---------------------------------------------------------------


def tokenize(plain: str, bold=False, italic=False, mono=False) -> list[Run]:
    runs: list[Run] = []
    pos = 0
    for m in INLINE_RE.finditer(plain):
        if m.start() > pos:
            runs += _symbol_runs(plain[pos:m.start()], bold, italic, mono)
        seg = m.group(0)
        if seg.startswith("`"):
            runs.append({"text": seg[1:-1], "bold": False, "italic": False,
                         "mono": True, "color": None})
        elif seg.startswith("**"):
            runs.append({"text": seg[2:-2], "bold": True, "italic": italic,
                         "mono": mono, "color": None})
        else:
            runs.append({"text": seg[1:-1], "bold": bold, "italic": True,
                         "mono": mono, "color": None})
        pos = m.end()
    if pos < len(plain):
        runs += _symbol_runs(plain[pos:], bold, italic, mono)
    return runs


def _symbol_runs(text: str, bold: bool, italic: bool, mono: bool) -> list[Run]:
    """Split badge emoji and check/cross marks into colored runs."""
    runs: list[Run] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf:
            runs.append({"text": buf, "bold": bold, "italic": italic,
                         "mono": mono, "color": None})
            buf = ""

    for ch in text:
        if ch in BADGE:
            flush()
            color, glyph = BADGE[ch]
            runs.append({"text": glyph, "bold": bold, "italic": italic,
                         "mono": mono, "color": color})
        elif ch in TICK:
            flush()
            runs.append({"text": ch, "bold": True, "italic": italic,
                         "mono": mono, "color": TICK[ch]})
        else:
            buf += ch
    flush()
    return runs


def runs_of(text: str) -> list[Run]:
    return tokenize(text)


def _same_style(a: Run, b: Run) -> bool:
    return (a["bold"] == b["bold"] and a["italic"] == b["italic"]
            and a["mono"] == b["mono"] and a["color"] == b["color"])


# --- renderer ------------------------------------------------------------------


class Deck(FPDF):
    def __init__(self):
        # fpdf2 expects the format tuple in portrait order (short side first),
        # then applies the orientation swap: -> 338.667 x 190.5 mm landscape.
        super().__init__(orientation="L", unit="mm", format=(PAGE_H, PAGE_W))
        if abs(self.w - PAGE_W) > 0.01 or abs(self.h - PAGE_H) > 0.01:
            raise RuntimeError(f"page geometry wrong: got {self.w:.1f}x{self.h:.1f}mm")
        self.set_auto_page_break(False)
        self.set_margins(MARGIN, MARGIN, MARGIN)
        for (fam, style), path in FONTS.items():
            self.add_font(fam, style=style, fname=path)

    # -- primitives --

    def _font_for(self, run, size):
        fam = "DejaVuMono" if run["mono"] else "DejaVu"
        style = ("B" if run["bold"] else "") + ("I" if run["italic"] else "")
        self.set_font(fam, style, size)

    def run_width(self, run, size) -> float:
        self._font_for(run, size)
        return self.get_string_width(run["text"])

    def draw_runs_line(self, runs, x, y, size):
        """Render pre-wrapped runs on one baseline; returns end x."""
        cx = x
        for run in runs:
            self._font_for(run, size)
            self.set_text_color(*(run["color"] or INK))
            self.set_xy(cx, y)
            self.cell(0, 0, run["text"], new_x=XPos.LMARGIN, new_y=YPos.TOP)
            cx += self.get_string_width(run["text"])
        return cx

    def wrap_runs(self, runs, size, max_w) -> list[list[Run]]:
        """Greedy word wrap over styled runs (whitespace kept as its own tokens)."""
        words: list[tuple[str, Run]] = []
        for run in runs:
            for p in re.split(r"(\s+)", run["text"]):
                if p:
                    words.append((p, run))
        lines, cur, cur_w = [], [], 0.0
        for wtxt, run in words:
            w = self.run_width({**run, "text": wtxt}, size)
            if wtxt.isspace():
                if cur:
                    cur.append((wtxt, run))
                    cur_w += w
                continue
            if cur and cur_w + w > max_w:
                # close the line, dropping its trailing whitespace
                while cur and cur[-1][0].isspace():
                    cur_w -= self.run_width({**cur[-1][1], "text": cur[-1][0]}, size)
                    cur.pop()
                lines.append(cur)
                cur, cur_w = [], 0.0
            cur.append((wtxt, run))
            cur_w += w
        while cur and cur[-1][0].isspace():
            cur.pop()
        if cur:
            lines.append(cur)
        return [self._merge(line) for line in lines if line]

    @staticmethod
    def _merge(pairs):
        runs = []
        for wtxt, run in pairs:
            if runs and _same_style(runs[-1], run):
                runs[-1]["text"] += wtxt
            else:
                runs.append({**run, "text": wtxt})
        return runs

    # -- slide chrome --

    def add_slide_chrome(self, slide, idx, total):
        self.add_page()
        if idx == 1:
            return
        y = MARGIN
        if slide["kicker"]:
            self.set_font("DejaVu", "B", 9)
            self.set_text_color(*ACCENT)
            self.set_xy(MARGIN, y)
            self.cell(0, 5, slide["kicker"], new_x=XPos.LMARGIN, new_y=YPos.TOP)
            y += 6.5
        self.set_font("DejaVu", "B", 21)
        self.set_text_color(*INK)
        self.set_xy(MARGIN, y)
        self.cell(0, 11, slide["title"], new_x=XPos.LMARGIN, new_y=YPos.TOP)
        y += 13.5
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.8)
        self.line(MARGIN, y, MARGIN + 24, y)
        # footer
        self.set_draw_color(*HAIRLINE)
        self.set_line_width(0.25)
        self.line(MARGIN, PAGE_H - 13, PAGE_W - MARGIN, PAGE_H - 13)
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*MUTED)
        self.set_xy(MARGIN, PAGE_H - 11)
        self.cell(0, 5, "Incident Postmortem Generator · IBM Bob 2.0 hackathon (lablab.ai)",
                  new_x=XPos.LMARGIN, new_y=YPos.TOP, align="L")
        self.set_xy(PAGE_W - MARGIN - 90, PAGE_H - 11)
        self.cell(90, 5, f"github.com/el-informatico/postmortem-generator · {idx}/{total}",
                  new_x=XPos.LMARGIN, new_y=YPos.TOP, align="R")

    # -- blocks --

    def bullets_block(self, bullets, y, size=10.8, leading=6.6, max_w=None, mark=True):
        max_w = max_w or (PAGE_W - 2 * MARGIN)
        for b in bullets:
            lines = self.wrap_runs(runs_of(b), size, max_w - (7 if mark else 0))
            if mark:
                self.set_fill_color(*ACCENT)
                self.rect(MARGIN, y + 1.7, 1.7, 1.7, style="F")
            for ln in lines:
                self.draw_runs_line(ln, MARGIN + (7 if mark else 0), y, size)
                y += leading
            y += 1.6
        return y

    def table_block(self, rows, y, size=9.4, leading=5.6):
        pad_x, pad_y = 2.6, 2.1
        plain = {"bold": False, "italic": False, "mono": False, "color": None}
        widths = []
        for col in range(len(rows[0])):
            w = max(self.run_width({**plain, "text": row[col]}, size) for row in rows)
            widths.append(w)
        usable = PAGE_W - 2 * MARGIN
        scale = usable / sum(widths)
        widths = [max(w * scale, 16.0) for w in widths]
        widths = [w * usable / sum(widths) for w in widths]
        for ri, row in enumerate(rows):
            header = ri == 0
            wrapped = [self.wrap_runs(runs_of(c), size, widths[ci] - 2 * pad_x)
                       for ci, c in enumerate(row)]
            row_h = max(len(c) for c in wrapped) * leading + 2 * pad_y
            if header:
                self.set_fill_color(*HEADER_BG)
                self.rect(MARGIN, y, usable, row_h, style="F")
            x = MARGIN
            for ci, cell_lines in enumerate(wrapped):
                yy = y + pad_y
                for ln in cell_lines:
                    runs = [{**r, "bold": True} for r in ln] if header else ln
                    self.draw_runs_line(runs, x + pad_x, yy, size)
                    yy += leading
                x += widths[ci]
            y += row_h
            self.set_draw_color(*HAIRLINE)
            self.set_line_width(0.25)
            self.line(MARGIN, y, PAGE_W - MARGIN, y)
        return y + 4

    def architecture_block(self, bullets, y):
        boxes, notes = [], []
        for b in bullets:
            m = re.match(r"^(\d+)\.\s+(.+?)\s+—\s+(.*)$", b)
            if m and len(boxes) < 4:
                boxes.append(m.groups())
            else:
                notes.append(re.sub(r"^\d+\.\s*", "", b))
        if len(boxes) != 4:
            raise ValueError(f"architecture layout expects 4 numbered boxes, got {len(boxes)}")
        gap = 9.0
        bw = (PAGE_W - 2 * MARGIN - 3 * gap) / 4
        bh = 52.0
        for i, (num, name, detail) in enumerate(boxes):
            x = MARGIN + i * (bw + gap)
            hot = name.startswith("IBM BOB")
            self.set_fill_color(*(BOB_FILL if hot else PANEL))
            self.set_draw_color(*(ACCENT if hot else HAIRLINE))
            self.set_line_width(0.65 if hot else 0.35)
            self.rect(x, y, bw, bh, style="DF", round_corners=True, corner_radius=2.5)
            self.set_fill_color(*ACCENT)
            self.ellipse(x + 4, y + 4, 7, 7, style="F")
            self.set_font("DejaVu", "B", 9)
            self.set_text_color(255, 255, 255)
            self.set_xy(x + 4, y + 5.6)
            self.cell(7, 4, num, new_x=XPos.LMARGIN, new_y=YPos.TOP, align="C")
            self.set_font("DejaVu", "B", 10.2)
            self.set_text_color(*INK)
            self.set_xy(x + 4, y + 14)
            self.cell(bw - 8, 5, name, new_x=XPos.LMARGIN, new_y=YPos.TOP)
            dy = y + 21
            for ln in self.wrap_runs(runs_of(detail), 7.9, bw - 8):
                self.draw_runs_line(ln, x + 4, dy, 7.9)
                dy += 4.6
            if i < 3:  # arrow to the next box
                ax0, ax1 = x + bw + 1.2, x + bw + gap - 1.2
                ay = y + bh / 2
                self.set_draw_color(*MUTED)
                self.set_line_width(0.5)
                self.line(ax0, ay, ax1, ay)
                self.line(ax1, ay, ax1 - 1.6, ay - 1.3)
                self.line(ax1, ay, ax1 - 1.6, ay + 1.3)
        return y + bh + 10, notes

    # -- whole slides --

    def render_title(self, slide):
        cy = 46.0
        self.set_font("DejaVu", "B", 9)
        self.set_text_color(*ACCENT)
        self.set_xy(MARGIN, cy)
        self.cell(PAGE_W - 2 * MARGIN, 5, slide["kicker"], align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.TOP)
        cy += 14
        self.set_font("DejaVu", "B", 28)
        self.set_text_color(*INK)
        self.set_xy(MARGIN, cy)
        self.cell(PAGE_W - 2 * MARGIN, 14, slide["title"], align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.TOP)
        cy += 22
        for ln in self.wrap_runs(runs_of(slide["subtitle"]), 12.5, 250):
            x = (PAGE_W - sum(self.run_width(r, 12.5) for r in ln)) / 2
            self.draw_runs_line(ln, x, cy, 12.5)
            cy += 7.2
        cy += 12
        for b in slide["bullets"]:
            size = 10.2
            for ln in self.wrap_runs(runs_of(b), size, 280):
                x = (PAGE_W - sum(self.run_width(r, size) for r in ln)) / 2
                self.draw_runs_line(ln, x, cy, size)
            cy += 6.4
        cy += 3.4

    def render(self, slides):
        total = len(slides)
        for idx, slide in enumerate(slides, 1):
            self.add_slide_chrome(slide, idx, total)
            if idx == 1:
                self.render_title(slide)
                continue
            y = MARGIN + (6.5 if slide["kicker"] else 0) + 13.5 + 7
            if slide["layout"] == "architecture":
                y, notes = self.architecture_block(slide["bullets"], y)
                self.bullets_block(notes, y, size=9.8, leading=6.0)
            else:
                if slide["bullets"]:
                    y = self.bullets_block(slide["bullets"], y)
                if slide["table"]:
                    y = self.table_block(slide["table"], y)
                if slide["post_bullets"]:
                    y = self.bullets_block(slide["post_bullets"], y)
            if y > PAGE_H - 16:
                raise ValueError(f"slide {idx} ({slide['title']!r}) overflows: y={y:.1f}")


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC_DEFAULT
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT_DEFAULT
    slides = parse_slides(src.read_text(encoding="utf-8"))
    deck = Deck()
    deck.set_title("Honest Postmortems from Repository Evidence — IBM Bob 2.0 hackathon")
    deck.set_author("el-informatico")
    deck.set_subject("Incident Postmortem Generator — hackathon submission deck (lablab.ai, Sep 2026)")
    deck.set_creator("scripts/build_deck.py")
    deck.set_keywords("postmortem, SZZ, IBM Bob 2.0, incident analysis, evidence linkage")
    deck.render(slides)
    out.parent.mkdir(parents=True, exist_ok=True)
    deck.output(out)
    print(f"OK {out} — {len(slides)} slides, {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
