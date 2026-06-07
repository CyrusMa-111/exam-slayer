#!/usr/bin/env python3
"""One-command exam cram pipeline for mixed material folders."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract mixed files, analyze high-frequency topics, and build an Exam Slayer pack.")
    parser.add_argument("materials_dir", help="Folder containing PDFs, PPTX, DOCX, images, text files, past papers, syllabus, etc.")
    parser.add_argument("--out", default=None, help="Output directory. Defaults to <materials_dir>/__exam_slayer__.")
    parser.add_argument("--time-budget", default="1 day", help="2 hours, 1 day, 3 days, or 1 week.")
    parser.add_argument("--target", default="pass", choices=["pass", "good", "high"], help="Target score strategy.")
    args = parser.parse_args()

    root = Path(args.materials_dir).resolve()
    if not root.is_dir():
        raise SystemExit(f"Directory not found: {root}")
    out_dir = Path(args.out).resolve() if args.out else root / "__exam_slayer__"
    extracted_dir = out_dir / "extracted_text"

    run([sys.executable, str(SCRIPT_DIR / "ingest_materials.py"), str(root), "--out", str(extracted_dir)])
    run([sys.executable, str(SCRIPT_DIR / "analyze_exam_frequency.py"), str(extracted_dir), "--out", str(out_dir)])
    run([
        sys.executable,
        str(SCRIPT_DIR / "build_slayer_pack.py"),
        str(out_dir / "exam_profile.json"),
        "--out",
        str(out_dir),
        "--time-budget",
        args.time_budget,
        "--target",
        args.target,
    ])

    print(f"[OK] Complete Exam Slayer pack: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

