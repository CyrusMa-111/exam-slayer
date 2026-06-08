#!/usr/bin/env python3
"""Detect and extract usable text from mixed exam-material folders.

The script accepts a folder containing any mix of text, Markdown, CSV/TSV,
DOCX, PPTX, PDF, and common image files. It writes extracted UTF-8 text files
to an output directory and records unsupported or failed files in a manifest.

It uses robust standard-library extractors for DOCX/PPTX and optional local
tools for PDF/OCR when available:
- PDF: PyMuPDF, pypdf/PyPDF2, or pdftotext command
- Images/scanned pages: pytesseract or tesseract command when available
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".log"}
DOCX_EXTENSIONS = {".docx"}
PPTX_EXTENSIONS = {".pptx"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SKIP_DIRS = {"__MACOSX", ".git", "node_modules", "__pycache__"}
KIND_LABELS = {"text": "文本", "docx": "Word 文档", "pptx": "PPT 课件", "pdf": "PDF", "image": "图片", "unsupported": "不支持"}
STATUS_LABELS = {"ok": "成功", "skipped": "跳过", "failed": "失败", "empty": "空文本"}
QUALITY_LABELS = {"ok": "正常", "missing": "未抽取", "suspect": "疑似乱码", "thin": "内容过少", "ocr": "OCR 待核对", "unknown": "未知"}
PDF_VISUAL_RENDER_DPI = 160
DEFAULT_MAX_RENDERED_PAGES = 30


def looks_garbled(text: str) -> bool:
    if not text:
        return False
    sample = text[:2000]
    replacement_count = sample.count("\ufffd") + sample.count("�")
    cid_count = sample.lower().count("(cid:")
    control_count = sum(1 for ch in sample if ord(ch) < 32 and ch not in "\n\r\t")
    return replacement_count >= 5 or cid_count >= 3 or control_count > max(10, len(sample) // 20)


def assess_quality(kind: str, text: str) -> tuple[str, bool, str]:
    chars = len(text.strip())
    if chars == 0:
        if kind in {"image", "pdf"}:
            return "missing", True, "没有抽取到文字；需要多模态模型查看原文件，或使用 OCR。"
        return "missing", False, "没有抽取到文字。"
    if looks_garbled(text):
        return "suspect", True, "抽取文本疑似乱码；需要对照原文件或使用多模态模型核对。"
    if chars < 80 and kind in {"pdf", "pptx", "docx", "image"}:
        return "thin", True, "抽取文本很少；原文件可能是扫描件、图片型材料或复杂版式。"
    if kind == "image":
        return "ocr", True, "图片 OCR 可能不准确；如有多模态模型，建议复核。"
    return "ok", False, ""


def safe_stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff._-]+", "_", path.stem).strip("_")
    return stem or "material"


def read_text_file(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="ignore")


def extract_csv_tsv(path: Path) -> str:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    text = read_text_file(path)
    rows = []
    for row in csv.reader(text.splitlines(), delimiter=delimiter):
        rows.append(" | ".join(cell.strip() for cell in row if cell.strip()))
    return "\n".join(row for row in rows if row.strip())


def xml_text_from_zip(path: Path, members: list[str]) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for member in members:
            try:
                data = zf.read(member)
            except KeyError:
                continue
            try:
                root = ET.fromstring(data)
            except ET.ParseError:
                continue
            texts = []
            for elem in root.iter():
                tag = elem.tag.rsplit("}", 1)[-1]
                if tag in {"t", "instrText"} and elem.text:
                    texts.append(elem.text)
                elif tag in {"tab"}:
                    texts.append("\t")
                elif tag in {"br", "cr"}:
                    texts.append("\n")
            if texts:
                chunks.append("\n".join(t.strip() for t in texts if t.strip()))
    return "\n\n".join(chunks)


def extract_docx(path: Path) -> str:
    members = ["word/document.xml"]
    with zipfile.ZipFile(path) as zf:
        members.extend(sorted(m for m in zf.namelist() if m.startswith("word/header") or m.startswith("word/footer")))
    return xml_text_from_zip(path, members)


def extract_pptx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        slide_members = sorted(
            (m for m in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", m)),
            key=lambda m: int(re.search(r"slide(\d+)\.xml", m).group(1)),
        )
        notes_members = sorted(m for m in zf.namelist() if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", m))
    chunks = []
    for member in slide_members:
        slide_no = re.search(r"slide(\d+)\.xml", member).group(1)
        text = xml_text_from_zip(path, [member])
        if text.strip():
            chunks.append(f"## Slide {slide_no}\n{text}")
    notes_text = xml_text_from_zip(path, notes_members)
    if notes_text.strip():
        chunks.append(f"## Speaker Notes\n{notes_text}")
    return "\n\n".join(chunks)


def extract_pdf_with_pymupdf(path: Path) -> str | None:
    try:
        import fitz  # type: ignore
    except Exception:
        return None
    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc, 1):
        text = page.get_text("text")
        if text.strip():
            pages.append(f"## Page {i}\n{text}")
    doc.close()
    return "\n\n".join(pages)


def extract_pdf_with_pypdf(path: Path) -> str | None:
    reader_cls = None
    try:
        from pypdf import PdfReader  # type: ignore
        reader_cls = PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
            reader_cls = PdfReader
        except Exception:
            return None
    reader = reader_cls(str(path))
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"## Page {i}\n{text}")
    return "\n\n".join(pages)


def extract_pdf_with_pdftotext(path: Path) -> str | None:
    if not shutil.which("pdftotext"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".txt") as tmp:
        result = subprocess.run(["pdftotext", str(path), tmp.name], capture_output=True, text=True)
        if result.returncode != 0:
            return None
        return Path(tmp.name).read_text(encoding="utf-8", errors="ignore")


def extract_pdf(path: Path) -> str:
    for extractor in (extract_pdf_with_pymupdf, extract_pdf_with_pypdf, extract_pdf_with_pdftotext):
        try:
            text = extractor(path)
        except Exception:
            text = None
        if text and text.strip():
            return text
    return ""


def count_pdf_pages(path: Path) -> int | None:
    try:
        import fitz  # type: ignore
    except Exception:
        return None
    try:
        doc = fitz.open(path)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return None


def render_pdf_pages(path: Path, out_dir: Path, max_pages: int = DEFAULT_MAX_RENDERED_PAGES) -> list[str]:
    """Render PDF pages to PNG files for vision-model review.

    Returns paths relative to out_dir. Requires PyMuPDF. If unavailable, returns
    an empty list. This is not OCR; it creates visual assets for later review.
    """
    try:
        import fitz  # type: ignore
    except Exception:
        return []

    visual_root = out_dir / "visual_assets" / safe_stem(path)
    visual_root.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []
    doc = fitz.open(path)
    zoom = PDF_VISUAL_RENDER_DPI / 72
    matrix = fitz.Matrix(zoom, zoom)
    try:
        for index, page in enumerate(doc, 1):
            if index > max_pages:
                break
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = visual_root / f"page_{index:03d}.png"
            pix.save(image_path)
            rendered.append(str(image_path.relative_to(out_dir)))
    finally:
        doc.close()
    return rendered


def extract_image(path: Path) -> str:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        text = pytesseract.image_to_string(Image.open(path), lang="chi_sim+eng")
        return text or ""
    except Exception:
        pass

    if shutil.which("tesseract"):
        result = subprocess.run(["tesseract", str(path), "stdout", "-l", "chi_sim+eng"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
    return ""


def classify_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in DOCX_EXTENSIONS:
        return "docx"
    if ext in PPTX_EXTENSIONS:
        return "pptx"
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "unsupported"


def extract_one(path: Path) -> tuple[str, str]:
    kind = classify_file(path)
    if kind == "text":
        if path.suffix.lower() in {".csv", ".tsv"}:
            return kind, extract_csv_tsv(path)
        return kind, read_text_file(path)
    if kind == "docx":
        return kind, extract_docx(path)
    if kind == "pptx":
        return kind, extract_pptx(path)
    if kind == "pdf":
        return kind, extract_pdf(path)
    if kind == "image":
        return kind, extract_image(path)
    return kind, ""


def iter_material_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS or (part.startswith("__cram") or part.startswith("__exam_slayer")) for part in path.parts):
            continue
        yield path


def should_render_visual_pages(kind: str, quality: str, render_mode: str) -> bool:
    if kind != "pdf":
        return False
    if render_mode == "never":
        return False
    if render_mode == "always":
        return True
    return quality in {"missing", "thin", "suspect"}


def ingest(root: Path, out_dir: Path, render_pdf_pages_mode: str = "auto", max_rendered_pages: int = DEFAULT_MAX_RENDERED_PAGES) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "root": str(root),
        "output_dir": str(out_dir),
        "render_pdf_pages": render_pdf_pages_mode,
        "max_rendered_pages": max_rendered_pages,
        "files": [],
    }
    used_names: dict[str, int] = {}

    for path in iter_material_files(root):
        rel = str(path.relative_to(root))
        kind = classify_file(path)
        record = {
            "path": rel,
            "kind": kind,
            "status": "skipped",
            "chars": 0,
            "output": None,
            "quality": "unknown",
            "needs_visual_review": False,
            "visual_reason": "",
            "visual_assets": [],
            "page_count": None,
        }
        if kind == "unsupported":
            record["reason"] = f"暂不支持的扩展名：{path.suffix}"
            manifest["files"].append(record)
            continue

        try:
            _, text = extract_one(path)
        except Exception as exc:
            record["status"] = "failed"
            record["reason"] = str(exc)
            manifest["files"].append(record)
            continue

        text = text.strip()
        quality, needs_visual_review, visual_reason = assess_quality(kind, text)
        record["quality"] = quality
        record["needs_visual_review"] = needs_visual_review
        record["visual_reason"] = visual_reason
        if kind == "pdf":
            record["page_count"] = count_pdf_pages(path)
            if should_render_visual_pages(kind, quality, render_pdf_pages_mode):
                assets = render_pdf_pages(path, out_dir, max_rendered_pages)
                record["visual_assets"] = assets
                if assets:
                    record["needs_visual_review"] = True
                    reason = "已将 PDF 页面渲染为图片，供多模态模型复核公式、图表、图标和复杂版式。"
                    record["visual_reason"] = f"{visual_reason} {reason}".strip()
                elif render_pdf_pages_mode in {"auto", "always"} and quality in {"missing", "thin", "suspect"}:
                    record["visual_reason"] = f"{visual_reason} 未能渲染 PDF 页面；请安装 PyMuPDF 或手动提供页面截图。".strip()
        if not text:
            record["status"] = "empty"
            record["reason"] = visual_reason or "没有抽取到文字。"
            manifest["files"].append(record)
            continue

        base = safe_stem(path)
        used_names[base] = used_names.get(base, 0) + 1
        suffix = f"_{used_names[base]}" if used_names[base] > 1 else ""
        out_path = out_dir / f"{base}{suffix}.txt"
        header = f"# 来源文件：{rel}\n\n"
        out_path.write_text(header + text + "\n", encoding="utf-8")
        record.update({"status": "ok", "chars": len(text), "output": str(out_path.name)})
        manifest["files"].append(record)

    (out_dir / "ingest_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def write_summary(manifest: dict, out_dir: Path) -> None:
    lines = ["# 材料摄取报告", "", "| 文件 | 类型 | 状态 | 质量 | 需要视觉复核 | 字符数 | 视觉资产 | 输出/原因 |", "|------|------|------|------|--------------|--------|----------|-----------|"]
    for item in manifest["files"]:
        detail = item.get("output") or item.get("reason") or ""
        visual = "是" if item.get("needs_visual_review") else ""
        visual_assets = len(item.get("visual_assets") or [])
        visual_asset_label = f"{visual_assets} 页" if visual_assets else ""
        kind = KIND_LABELS.get(item["kind"], item["kind"])
        status = STATUS_LABELS.get(item["status"], item["status"])
        quality = QUALITY_LABELS.get(item.get("quality", ""), item.get("quality", ""))
        lines.append(f"| {item['path']} | {kind} | {status} | {quality} | {visual} | {item['chars']} | {visual_asset_label} | {detail} |")
    (out_dir / "ingest_summary.md").write_text("\n".join(lines), encoding="utf-8")


def write_visual_review_queue(manifest: dict, out_dir: Path) -> None:
    items = [f for f in manifest["files"] if f.get("needs_visual_review")]
    lines = [
        "# 需要视觉/OCR 复核的文件",
        "",
        "这些文件在进入高频考点分析前，可能需要多模态模型查看原文件，或使用更强的 OCR。",
        "",
    ]
    if not items:
        lines.append("没有文件被标记为需要视觉复核。")
    else:
        lines.extend(["| 文件 | 类型 | 状态 | 质量 | 视觉资产 | 原因 |", "|------|------|------|------|----------|------|"])
        for item in items:
            reason = item.get("visual_reason") or item.get("reason") or ""
            kind = KIND_LABELS.get(item["kind"], item["kind"])
            status = STATUS_LABELS.get(item["status"], item["status"])
            quality = QUALITY_LABELS.get(item.get("quality", ""), item.get("quality", ""))
            assets = item.get("visual_assets") or []
            asset_text = ", ".join(assets[:3])
            if len(assets) > 3:
                asset_text += f" ... 共 {len(assets)} 页"
            lines.append(f"| {item['path']} | {kind} | {status} | {quality} | {asset_text} | {reason} |")
        lines.extend([
            "",
            "建议处理方式：",
            "- 如果当前模型可以看图片/PDF 页面，请优先查看 `visual_assets/` 中的页面图，补充公式、图表、图标、流程图和复杂版式内容。",
            "- 对公式和图表，不要只转写散乱文字；请总结其含义、变量、坐标轴、趋势、结论和可能考法。",
            "- 如果当前模型是纯文本模型，请安装 Tesseract 等 OCR 工具，或提供文字版材料。",
            "- 补充恢复文本后，重新运行 `analyze_exam_frequency.py` 和 `build_slayer_pack.py`。",
        ])
    (out_dir / "needs_visual_review.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text from mixed exam material folders.")
    parser.add_argument("materials_dir", help="Folder containing any mix of exam materials.")
    parser.add_argument("--out", default=None, help="Output text directory. Defaults to <materials_dir>/__exam_slayer__/extracted_text.")
    parser.add_argument("--render-pdf-pages", choices=["auto", "always", "never"], default="auto", help="Render PDF pages to PNG for vision review. auto renders failed/thin/garbled PDFs.")
    parser.add_argument("--max-rendered-pages", type=int, default=DEFAULT_MAX_RENDERED_PAGES, help="Maximum PDF pages to render per file when visual rendering is enabled.")
    args = parser.parse_args()

    root = Path(args.materials_dir).resolve()
    if not root.is_dir():
        raise SystemExit(f"Directory not found: {root}")
    out_dir = Path(args.out).resolve() if args.out else root / "__exam_slayer__" / "extracted_text"

    manifest = ingest(root, out_dir, args.render_pdf_pages, args.max_rendered_pages)
    write_summary(manifest, out_dir)
    write_visual_review_queue(manifest, out_dir)
    ok = sum(1 for f in manifest["files"] if f["status"] == "ok")
    failed = sum(1 for f in manifest["files"] if f["status"] in {"failed", "empty"})
    skipped = sum(1 for f in manifest["files"] if f["status"] == "skipped")
    print(f"[OK] Extracted {ok} files to {out_dir}")
    if failed:
        print(f"[WARN] {failed} files had no extracted text or failed; see ingest_summary.md")
    visual = sum(1 for f in manifest["files"] if f.get("needs_visual_review"))
    if visual:
        print(f"[WARN] {visual} files need visual/OCR review; see needs_visual_review.md")
    if skipped:
        print(f"[INFO] {skipped} unsupported files skipped; see ingest_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
