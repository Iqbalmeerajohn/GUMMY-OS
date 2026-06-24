# PDF Export — GUMMY OS Master Document

> No offline PDF toolchain (pandoc / wkhtmltopdf) is installed in this
> environment, so a PDF was **not** generated automatically. The canonical export
> source is [`GUMMY_OS_MASTER_DOCUMENT.md`](GUMMY_OS_MASTER_DOCUMENT.md), which is
> written to convert cleanly. Pick whichever path below is convenient.

## Option A — Pandoc (best quality, needs LaTeX/wkhtmltopdf)

```bash
# install once: https://pandoc.org/installing.html  (+ a PDF engine)
pandoc docs/GUMMY_OS_MASTER_DOCUMENT.md \
  -o docs/GUMMY_OS_MASTER_DOCUMENT.pdf \
  --toc --pdf-engine=wkhtmltopdf -V geometry:margin=2.5cm
```

## Option B — VS Code (no CLI)

1. Install the **"Markdown PDF"** extension (yzane.markdown-pdf).
2. Open `docs/GUMMY_OS_MASTER_DOCUMENT.md`.
3. Command Palette → **"Markdown PDF: Export (pdf)"**.

## Option C — Browser print (zero install)

1. Open the `.md` in any Markdown previewer (e.g. GitHub, or VS Code preview).
2. **Print → Save as PDF** (A4/Letter, margins ~2cm).

## Option D — Node one-liner (if you prefer npm)

```bash
npx md-to-pdf docs/GUMMY_OS_MASTER_DOCUMENT.md   # writes the .pdf alongside
```

---

The same commands work for any other doc in this folder (e.g.
`RESUME_PROJECT_SUMMARY.md` for a printable résumé attachment).
