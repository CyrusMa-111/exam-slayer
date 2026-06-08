# Output Quality Gates

Use this checklist before delivering a substantial Exam Slayer pack.

## Evidence

- High-priority topics cite past paper years or source files.
- Topics based only on slides/notes are not labeled high-frequency unless supported by past papers.
- Conflicting answer keys or source disagreements are called out.
- Missing materials are listed as limitations.

## Prioritization

- The top topics are ranked, not merely listed.
- The ranking considers frequency, recency, question type, likely points, and source strength.
- The plan is realistic for the time budget.
- Low-yield topics are explicitly deferred when the target is pass or time is short.

## Usability

- The output is short enough for the user's remaining time.
- It starts with what to do first.
- It contains fast-review artifacts: formulas, definitions, templates, pitfalls, or flashcards.
- Practice questions map back to high-priority topics.
- LaTeX formulas render cleanly. Long formulas use standalone `$$...$$` blocks with blank lines around them.
- No generated Markdown contains unmatched `$`, `$$`, `\(`, `\)`, `\[`, or `\]` delimiters. Run `scripts/validate_latex_markdown.py` when scripts are available.

## Subject Fit

- Humanities outputs include answer frameworks and scoring points.
- Calculation outputs include formula triggers and worked templates.
- Programming outputs include tracing, complexity, and implementation patterns.
- Open-book outputs include a lookup index.
- Closed-book outputs include memory compression.

## Risk Report

Include a risk report when:
- No past papers are available.
- Only one year of papers is available.
- Answer keys conflict.
- The syllabus is missing.
- The user asks for prediction-level guidance.
