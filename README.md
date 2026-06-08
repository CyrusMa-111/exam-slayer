# Exam Slayer

一个考前续命包：把课件、考纲、历年真题、答案和笔记丢进文件夹，它会榨出高频考点，生成突击复习计划、速记稿、练习题和采分点。

## 适合场景

- 期末只剩几小时到几天，需要快速抓重点
- 想从历年试卷里找高频考点
- 想把课件、真题、考纲、答案混合材料整理成冲刺资料
- 想生成复习计划、速记稿、练习题、答案采分点和风险报告

## 功能

- 学科无关，不硬编码具体课程
- 支持混合资料文件夹
- 自动识别并抽取 `.txt`、`.md`、`.csv`、`.tsv`、`.docx`、`.pptx`、`.pdf`、常见图片格式
- 对扫描件/图片/疑似乱码文件生成视觉或 OCR 复核清单
- 从历年卷、考纲、答案中提取高频考点
- 默认中文输出
- 按 `2 hours`、`1 day`、`3 days`、`1 week` 生成不同粒度的考前续命包

## 安装到 Codex

把 skill 目录复制到 Codex skills 目录：

```bash
cp -R exam-slayer-skill ~/.codex/skills/
```

然后重启或刷新 Codex。

调用时使用 skill 名：

```text
exam-slayer
```

示例：

```text
用 exam-slayer 分析我的资料文件夹：/path/to/materials
我还有 1 天考试，目标保过。
```

## 直接运行脚本

也可以不安装到 Codex，直接运行一键流水线：

```bash
python3 exam-slayer-skill/scripts/run_exam_slayer.py "/path/to/materials" --time-budget "1 day" --target pass
```

如果 PDF 里有大量公式、图表、图标、曲线，建议强制渲染 PDF 页面，方便多模态模型后续复核：

```bash
python3 exam-slayer-skill/scripts/run_exam_slayer.py "/path/to/materials" --time-budget "1 day" --target pass --render-pdf-pages always
```

参数：

```text
--time-budget "2 hours" | "1 day" | "3 days" | "1 week"
--target pass | good | high
```

输出会生成在资料文件夹的 `__exam_slayer__/` 目录里。

## 资料怎么放

把所有材料放进同一个文件夹即可。文件名尽量带上年份和类型，方便识别：

```text
materials/
├── 2023期末真题.pdf
├── 2024期末真题.docx
├── 复习范围.png
├── 老师PPT.pptx
├── 习题答案.docx
├── 教材重点.pdf
└── 笔记.md
```

## 输出文件

```text
__exam_slayer__/
├── slayer_plan.md                期末突击复习计划
├── high_frequency_topics.md      高频考点报告
├── quick_review.md               考前速记稿
├── practice_set.md               针对性练习题
├── practice_answers.md           练习题答案与采分点
├── flashcards.csv                闪卡
├── risk_report.md                风险报告
└── extracted_text/
    ├── ingest_summary.md         材料摄取报告
    └── needs_visual_review.md    需要视觉/OCR 复核的文件
```

## 关于图片和扫描 PDF

普通文本型 PDF、DOCX、PPTX 通常可以直接抽取文字。

图片、扫描版 PDF、复杂版式、公式截图的准确性取决于 OCR 或多模态模型能力。如果某些文件抽取失败或抽取质量低，会写入：

```text
__exam_slayer__/extracted_text/needs_visual_review.md
```

如果当前模型支持视觉，可以根据这份清单补充识别；如果是纯文本模型，需要安装 OCR 工具或提供文字版材料。

当启用 PDF 页面渲染后，页面图片会放在：

```text
__exam_slayer__/extracted_text/visual_assets/
```

这些图片用于复核普通文本抽取容易漏掉的内容，比如公式、变量含义、坐标轴、趋势、图表结论、图标结构和曲线形状。

## 项目结构

```text
exam-slayer-skill/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── output_quality_gates.md
│   └── question_type_playbooks.md
└── scripts/
    ├── ingest_materials.py
    ├── analyze_exam_frequency.py
    ├── build_slayer_pack.py
    └── run_exam_slayer.py
```

## 贡献

欢迎提交 issue 或 pull request。比较适合贡献的方向：

- 更好的 PDF/OCR 抽取
- 更多题型策略
- 更准确的中文考点抽取
- 更好的模拟卷生成
- Anki/Quizlet 导出
