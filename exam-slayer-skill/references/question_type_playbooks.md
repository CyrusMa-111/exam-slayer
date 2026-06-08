# Question Type Playbooks

Use this reference only when adapting the Exam Slayer pack to a subject or exam format.

## Objective Questions

For single choice, multiple choice, and true/false:
- Extract repeated stems and options from past papers.
- Group questions by concept, not by exact wording.
- Make a "trap list": confusing terms, exception cases, negative wording, units, chronology, authors, formulas.
- Output fast drills with answer and one-line explanation.

## Short Answer

For each high-frequency short-answer topic:
- Give a 3-part answer skeleton: definition, key points, example/application.
- Mark scoring points explicitly.
- Provide a 30-second version and a full-mark version.

## Essay / Discussion / Case Analysis

For essay-like questions:
- Identify repeated themes and reusable argument structures.
- Build outlines instead of memorized paragraphs.
- Include transition phrases only when the subject benefits from them.
- Provide a "minimum pass answer" and "high-score extension".

## Calculation / Formula Problems

For calculation-heavy courses:
- Build a formula trigger table: when to use which formula.
- Show known quantities, unknown quantity, formula, substitution, result, and unit.
- Write formulas and substitutions in Markdown-compatible LaTeX.
- Include common traps: sign direction, denominator choice, compounding period, rounding, assumptions.
- Practice should prioritize repeated problem templates over random numbers.

Recommended LaTeX structure:

```markdown
### 公式触发

看到“信息增益 / entropy / purity”时，先写：

$$
H(D) = -\sum_{k=1}^{K} p_k \log_2 p_k
$$

- $D$：当前数据集
- $p_k$：第 $k$ 类样本占比
- $K$：类别数

### 代入模板

$$
H(D) = -\frac{4}{9}\log_2\frac{4}{9} - \frac{5}{9}\log_2\frac{5}{9}
$$
```

## Proof / Derivation

For proof-based courses:
- Extract theorem names and repeated proof patterns.
- Provide proof skeletons: assumptions, goal, key lemma, transformation, conclusion.
- Separate "must memorize" from "can reconstruct".
- Use LaTeX for all symbolic transformations.

## Programming / CS

For programming exams:
- Classify topics into concept recall, code tracing, debugging, algorithm design, complexity, and implementation.
- Include minimal implementation skeletons only for repeated patterns.
- For code tracing, output state tables.
- For complexity, include input size, dominant operation, and final Big-O.

## Open-Book Exams

For open-book exams:
- Focus on locating information quickly.
- Build an index of concepts, formulas, pages/slides, and example problems.
- Prioritize templates, navigation, and synthesis over memorization.

## Closed-Book Exams

For closed-book exams:
- Prioritize memory compression.
- Produce flashcards, mnemonics, formula sheets, and answer skeletons.
- Keep notes compact enough for repeated review.
