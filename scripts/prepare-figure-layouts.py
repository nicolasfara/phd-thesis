# /// script
# dependencies = ["pymupdf>=1.24"]
# ///
"""Prepare readable thesis figures without resampling or changing plotted data.

Run with ``uv run scripts/prepare-figure-layouts.py``. The generated PDFs are
checked in, so building the thesis does not require Python. Original PDFs remain
the source: convergence panels are cropped, density legends move into LaTeX,
and labels in the reward plots are enlarged.
"""

from pathlib import Path
import re

import pymupdf as fitz


FIGURES = Path(__file__).resolve().parents[1] / "figures"


def save(doc, name):
    doc.save(FIGURES / f"{name}.pdf", garbage=4, deflate=True, no_new_id=True)


def crop_convergence():
    for name in ("gradient-convergence", "gradient-convergence-error",
                 "scr-convergence", "scr-convergence-error"):
        source = fitz.open(FIGURES / f"{name}.pdf")
        rect = source[0].rect
        for column, nodes in enumerate((50, 100, 200)):
            clip = fitz.Rect(column * rect.width / 3, 0,
                             (column + 1) * rect.width / 3, rect.height)
            output = fitz.open()
            page = output.new_page(width=clip.width, height=clip.height)
            page.show_pdf_page(page.rect, source, 0, clip=clip)
            save(output, f"{name}-{nodes}")


def density_plots():
    for path in sorted(FIGURES.glob("idhgql-density-*.pdf")):
        if path.stem.endswith("-readable"):
            continue
        doc = fitz.open(path)
        page = doc[0]
        contents = page.get_contents()
        assert len(contents) == 1, path
        stream = doc.xref_stream(contents[0])
        # Matplotlib emits the legend last, after all points and axes. Remove
        # that complete block, revealing the original points underneath it.
        marker = b"/A3 gs 1 g"
        assert stream.count(marker) == 1, path
        drawing, legend = stream.split(marker)
        assert b"9.9626400996 Tf" in legend, path
        # Keep the existing font and tick positions; this small increase gives
        # seven-point tick labels when a panel occupies 48% of the text width.
        readable = drawing.replace(b"14.9439601494 Tf", b"16.5 Tf")
        # Every non-text drawing command is retained byte for byte.
        strip_text = lambda value: re.sub(rb"BT\b.*?\bET", b"", value, flags=re.S)
        assert strip_text(readable) == strip_text(drawing), path
        doc.update_stream(contents[0], readable)
        save(doc, f"{path.stem}-readable")


def put_text(page, text, x, y, size=7, align="center"):
    width = fitz.get_text_length(text, fontname="helv", fontsize=size)
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    page.insert_text((x, y), text, fontsize=size, fontname="helv")


def reward_plots():
    for suffix in ("battery", "cost", "server-load"):
        name = f"idhgql-edge-case-{suffix}"
        source = fitz.open(FIGURES / f"{name}.pdf")
        old = source[0]
        drawings = old.get_drawings()
        axes = sorted([
            d["rect"] for d in drawings
            if d["fill"] == (1., 1., 1.)
            and 400 < d["rect"].width < 600 and d["rect"].height > 300
        ], key=lambda r: r.x0)
        assert len(axes) == 3, name
        lines = [line for block in old.get_text("dict")["blocks"]
                 for line in block.get("lines", [])]
        numbers = []
        for line in lines:
            text = "".join(s["text"] for s in line["spans"]).replace("−", "-")
            if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
                numbers.append((fitz.Rect(line["bbox"]), text))
        output = fitz.open()
        page = output.new_page(width=416, height=149)
        # Keep the original weight heading, including its mathematical fonts.
        heading = fitz.Rect(0, 0, 0, 0)
        for line in lines:
            if line["bbox"][3] < 60:
                heading |= fitz.Rect(line["bbox"])
        assert not heading.is_empty, name
        heading += (-2, -2, 2, 2)
        heading &= old.rect
        page.show_pdf_page(fitz.Rect(125, 0, 291, 17), source, 0, clip=heading)
        for column, axis in enumerate(axes):
            left = 25 + column * 141
            target = fitz.Rect(left, 35, left + 100, 35 + 100 * axis.height / axis.width)
            # Copy the original curves, shading, grid, and axes as PDF objects.
            page.show_pdf_page(target, source, 0, clip=axis)
            title = ["Battery (%)", "Local components (%)", "Total cost"][column]
            if column == 1 and suffix == "server-load":
                title = "Edge-server components (%)"
            put_text(page, title, left + 50, 28, size=7.5)
            x_ticks = [d["rect"].x0 for d in drawings
                       if d["rect"].width < 0.1 and 0 < d["rect"].height < 5
                       and abs(d["rect"].y0 - axis.y1) < 1]
            y_ticks = [d["rect"].y0 for d in drawings
                       if 0 < d["rect"].width < 5 and d["rect"].height < 0.1
                       and abs(d["rect"].x1 - axis.x0) < 1]
            nx = ny = 0
            for bbox, text in numbers:
                cx, cy = (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2
                if axis.y1 <= bbox.y0 < axis.y1 + 60 and axis.x0 - 25 < cx < axis.x1 + 25:
                    tick = min(x_ticks, key=lambda x: abs(x - cx)) if x_ticks else cx
                    x = target.x0 + (tick - axis.x0) * target.width / axis.width
                    put_text(page, text, x, target.y1 + 10)
                    nx += 1
                elif axis.x0 - 15 < bbox.x1 < axis.x0 + 2 and axis.y0 - 25 < cy < axis.y1 + 25:
                    tick = min(y_ticks, key=lambda y: abs(y - cy)) if y_ticks else cy
                    y = target.y0 + (tick - axis.y0) * target.height / axis.height
                    put_text(page, text, target.x0 - 3, y + 2.4, align="right")
                    ny += 1
            assert nx >= 4 and ny >= 4, (name, column, nx, ny)
        put_text(page, "Global round", 216, 147, size=7.5)
        save(output, f"{name}-readable")


if __name__ == "__main__":
    crop_convergence()
    density_plots()
    reward_plots()
