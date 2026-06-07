---
name: exam-slayer
description: Use when the user needs short-term final exam cramming, rapid review, high-frequency topic mining from past papers, or an exam-focused study pack from course materials. Works across subjects and should not assume a specific course. Triggers on "期末速成", "突击复习", "临时抱佛脚", "高频考点", "历年试卷", "真题", "保过", "考前冲刺", "final exam slayer", or when the user provides past papers, syllabus, PPT, notes, exercises, textbook excerpts, or answer keys and asks what to review first.
metadata:
  short-description: Build high-yield Exam Slayer packs from course materials and past papers.
---

# Exam Slayer

## Purpose

Help the user maximize score under limited time. This skill is not a generic note organizer. It builds a high-yield Exam Slayer plan from available evidence: past papers, syllabus, slides, notes, textbook excerpts, exercises, and answer keys.

Core commitments:
- Course-agnostic: infer subject, chapters, question types, and exam format from materials.
- Time-aware: prioritize differently for 2 hours, 1 day, 3 days, or 1 week.
- Past-paper-driven: use recurring questions and high-frequency concepts as the main signal.
- Evidence-based: mark source files, years, confidence, and conflicts.
- Output-focused: produce concise review artifacts students can actually use before an exam.
- Chinese-first output: unless the user explicitly asks for English, write generated study plans, headings, explanations, answer templates, and reports in Chinese. Keep unavoidable source terms or technical terms in their original language when useful.

## Quick Workflow

1. Inventory materials.
2. Determine exam constraints: time left, target score, current level, open/closed book, allowed aids.
3. Analyze past papers first when available.
4. Build a weighted topic map from frequency, recency, points, source confidence, and user weakness.
5. Generate the smallest useful Exam Slayer pack for the time budget.
6. Verify coverage, evidence tags, and risky assumptions before delivery.

Default to the one-command pipeline when the user provides a folder of mixed materials:

```bash
python3 scripts/run_exam_slayer.py "<materials_dir>" --time-budget "1 day" --target "pass"
```

This pipeline:
1. Detects usable files in the folder.
2. Extracts text from supported formats.
3. Analyzes high-frequency topics.
4. Builds the Exam Slayer pack.

## Extraction Strategy

Treat ingestion as a layered process, not a promise that every model can read every file perfectly.

Layer 1: deterministic parsers
- Use scripts for text, CSV/TSV, DOCX, PPTX, and text-layer PDFs.
- This is fast and model-independent.

Layer 2: local OCR
- Use Tesseract or Python OCR packages for images and scanned PDFs when available.
- OCR quality depends on scan clarity, language packs, handwriting, layout, and formulas.

Layer 3: vision-capable model review
- If the current model/tooling can inspect images or PDF pages, use it for files listed in `needs_visual_review.md`.
- Transcribe or summarize exam-relevant content into `__exam_slayer__/extracted_text/`, then rerun the analysis and Exam Slayer scripts.

Text-only model fallback:
- If the active model cannot inspect images/PDF pages visually, do not claim those files were understood.
- Tell the user which files need OCR or a vision-capable model, using `needs_visual_review.md` and `ingest_summary.md` as evidence.

Supported direct inputs:
- Text-like: `.txt`, `.md`, `.markdown`, `.csv`, `.tsv`
- Office: `.docx`, `.pptx`
- PDF: `.pdf`
- Images/OCR when local OCR tools exist: `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, `.webp`

PDF and image extraction depends on local tools and/or vision-capable models. If a scanned PDF, image, formula-heavy page, or complex slide cannot be read, report the file in `ingest_summary.md` and `needs_visual_review.md`. Do not pretend unreadable files were analyzed.

Use step-by-step scripts only when debugging or when the user asks for manual control:

```bash
python3 scripts/ingest_materials.py "<materials_dir>" --out "<materials_dir>/__exam_slayer__/extracted_text"
python3 scripts/analyze_exam_frequency.py "<materials_dir>/__exam_slayer__/extracted_text" --out "<materials_dir>/__exam_slayer__"
python3 scripts/build_slayer_pack.py "<materials_dir>/__exam_slayer__/exam_profile.json" --out "<materials_dir>/__exam_slayer__" --time-budget "1 day" --target "pass"
```

The extractor uses standard-library DOCX/PPTX parsing and optional local tools for PDF/OCR. Always review `ingest_summary.md` and `needs_visual_review.md` before trusting the final Exam Slayer pack.

## Material Priority

Prefer sources in this order:

1. Past papers / 历年试卷 / 真题
2. Official exam outline / syllabus / 复习范围
3. Teacher slides, class notes, review sessions
4. Exercise banks and answer keys
5. Textbook excerpts
6. AI-generated practice only after evidence-backed topics are identified

If sources conflict, mark the conflict and prefer official outline or textbook over unofficial answers unless the user says otherwise.

## Slayer Modes

Choose a mode from time left. If unknown, ask one concise question. If the user wants immediate output, assume `1 day / pass`.

| Time left | Strategy | Output size |
|-----------|----------|-------------|
| 2 hours | Memorize only the highest-yield facts, formulas, templates, and repeated question answers | Very short |
| 1 day | Top topics, typical problems, answer templates, one fast self-test | Short |
| 3 days | Topic map, daily schedule, practice sets, weak-point repair | Medium |
| 1 week | Full Exam Slayer plan, staged tests, flashcards, mock exam blueprint | Larger |

Target score changes risk tolerance:
- `pass`: skip low-frequency topics aggressively.
- `good`: cover high and medium frequency topics.
- `high`: include low-frequency but high-point or conceptually central topics.

## High-Frequency Topic Scoring

When past papers exist, rank topics with this logic:

```
priority = frequency + recency + point_value + source_strength + weakness_boost - uncertainty_penalty
```

Minimum evidence to label a topic:
- `High`: repeated across years or appears in high-point questions.
- `Medium`: appears once in past papers and is supported by outline/slides.
- `Low`: appears only in course materials with no past-paper support.
- `Unverified`: inferred by the AI without direct evidence.

Always show why a topic is high priority: source files, years, repeated wording, question type, or point value.

## Outputs

Produce only the artifacts useful for the user's time budget. Do not overproduce.

Default language: Chinese. If course materials are English, keep technical terms in English but explain and organize the review pack in Chinese.

Recommended artifacts:
- `ingest_summary.md`: what files were recognized, extracted, skipped, or failed.
- `needs_visual_review.md`: files that need OCR, visual model review, or manual text export.
- `slayer_plan.md`: time-boxed plan with what to study first.
- `high_frequency_topics.md`: ranked high-yield concepts with evidence.
- `quick_review.md`: compact notes, formulas, definitions, and answer templates.
- `practice_set.md`: targeted questions from high-frequency areas.
- `flashcards.csv`: optional Q/A cards for memorization.
- `risk_report.md`: missing sources, low-confidence answers, conflicts, likely gaps.

For answer-heavy subjects, include scoring points. For calculation subjects, include formula selection, common traps, and worked templates. For programming subjects, include pattern recognition, code tracing, complexity, and common implementation skeletons.

## Subject-Agnostic Handling

Infer the subject family from materials and adapt output:

- Humanities/social science: definitions, short-answer templates, essay outlines, compare/contrast tables.
- Math/engineering/economics: formulas, derivation triggers, typical calculation templates, unit checks.
- Programming/computer science: concepts, code reading, algorithms, complexity, implementation patterns.
- Medicine/law/policy: cases, mechanisms, statutes/criteria, differential comparison tables.
- Language exams: vocabulary clusters, grammar traps, reading patterns, writing templates.

For detailed playbooks, read `references/question_type_playbooks.md` only when needed.

## Quality Gates

Before final delivery, check:

- Every high-priority topic has evidence tags.
- `needs_visual_review.md` has been handled or explicitly listed as a limitation.
- Past-paper claims include year or source filename when available.
- The plan matches the user's time budget.
- Low-confidence content is labeled instead of presented as fact.
- Practice questions map to the ranked topics.
- No course-specific hardcoding remains unless it came from the user's materials.

For a fuller checklist, read `references/output_quality_gates.md` when preparing a substantial deliverable.

## What To Avoid

- Do not generate a long textbook-style review when the user asked for cramming.
- Do not assume a subject, chapter list, or exam format from examples.
- Do not treat AI-generated topics as high-frequency evidence.
- Do not hide missing past papers; say when ranking is based only on syllabus/slides.
- Do not promise exact predictions. Frame high-frequency topics as evidence-backed priorities.
- Do not spend time beautifying PDFs before the study strategy is correct.
