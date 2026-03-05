---
description: Interactive paper review with annotation extraction, Bloom's taxonomy quiz, and spaced repetition
argument-hint: "[document-name-or-URL]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, AskUserQuestion]
model: claude-opus-4-6
---

# Paper Review Orchestrator

You run an interactive 3-stage paper review: **Understand → Quiz → Next Steps**. You manage the entire flow, using `AskUserQuestion` for all user interaction.

## Constants

- **Data repo**: `/Users/titus/pyg/paper-review`
- **Plugin root**: `${CLAUDE_PLUGIN_ROOT}`
- **Scripts run via**: `uv run --python 3.12 --with <deps> ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py`
- **Spaced repetition schedule**: [1, 3, 7, 14, 30, 90] days

## State Recovery

After each stage, write intermediate results to `papers/<slug>/` so later stages don't depend on context window. If you lose context, check for:
- `papers/<slug>/review-state.json` — overall state (current stage, slug, source)
- `papers/<slug>/stage1-notes.json` — Stage 1 output
- `papers/<slug>/stage2-quiz.json` — Stage 2 output

## Startup: Acquire the Paper

Parse `{{argument}}`:

### No argument
1. Check `/Users/titus/pyg/paper-review/database.json` for papers where `next_review` ≤ today — if any, mention them as due for spaced repetition re-review
2. Run `rmapi ls "To Quiz"` to list documents
3. Present the list via `AskUserQuestion` — let the user pick, or auto-pick if only one

### URL (starts with `http`)
1. Use `WebFetch` to get the content
2. Generate a slug from the page title
3. Create `mkdir -p /Users/titus/pyg/paper-review/papers/<slug>`
4. Save the web content — no PDF extraction needed, work from web content directly
5. Skip to Stage 1 with the web content as the source material

### Document name
1. Run `rmapi find "" "{{argument}}"` to locate it on the reMarkable
2. If ambiguous, present matches via `AskUserQuestion`

### reMarkable document download pipeline
1. Generate slug: lowercase, hyphenated, max 50 chars (e.g., `ai-control-improving-safety`)
2. `mkdir -p /Users/titus/pyg/paper-review/papers/<slug>`
3. `cd /Users/titus/pyg/paper-review/papers/<slug> && rmapi get "<full-path>"`
4. `unzip "*.zip" -d .` — extracts `<uuid>.pdf`, `<uuid>.content`, `<uuid>/<page-uuid>.rm` files
5. Run annotation extraction:
   ```
   uv run --python 3.12 --with rmscene,PyMuPDF ${CLAUDE_PLUGIN_ROOT}/scripts/extract_annotations.py /Users/titus/pyg/paper-review/papers/<slug>/
   ```
6. Parse the JSON output
7. For any ink annotations with `image_path`: use the Read tool to view the PNG images and transcribe the handwriting
8. Save state:
   ```json
   // papers/<slug>/review-state.json
   {"stage": 1, "slug": "<slug>", "source": "remarkable", "remarkable_path": "<path>", "title": "...", "annotations_file": "annotations.json"}
   ```
9. Save the annotation extraction output to `papers/<slug>/annotations.json`

## Stage 1: Understanding & Questions

**Goal**: Help the user understand the paper deeply by reviewing highlights, answering questions, and using the Feynman technique.

1. **Present highlights**: Group by page, show each highlight with its page number. For ink annotations, include the transcribed text.

2. **Identify question annotations**: Look for highlights containing "?", "why", "how", "what does", "what is", or other question-like patterns. Present these to the user as their own questions.

3. **Answer questions**: For each question the user raised (via annotations or interactively):
   - First try to answer from the paper content
   - If the paper doesn't fully address it, use `WebSearch` to find answers
   - Cite specific sections/pages when referencing the paper

4. **Feynman Technique**: Pick 2-3 key concepts from the highlights. For each:
   - Ask (via `AskUserQuestion`): "Explain [concept] as if teaching someone who has never encountered it."
   - Evaluate their explanation following the corrective feedback patterns from the learning science skill
   - Identify gaps: vague hand-waving, circular definitions, missing mechanisms

5. **Wrap up**: Ask "Ready to move to the quiz, or do you have more questions?"

6. **Save state**: Write `papers/<slug>/stage1-notes.json`:
   ```json
   {
     "questions_asked": [...],
     "feynman_concepts": [{"concept": "...", "user_explanation": "...", "gaps": [...], "feedback": "..."}],
     "key_themes": [...]
   }
   ```

## Stage 2: Quiz (Bloom's Taxonomy)

**Goal**: Test comprehension at progressively higher cognitive levels.

1. Load question stems from `${CLAUDE_PLUGIN_ROOT}/skills/learning-science/references/blooms-taxonomy.md`

2. Read `papers/<slug>/stage1-notes.json` if not in context — use identified themes and gaps to inform question selection

3. Generate and present questions in rounds:
   - **Round 1**: 2-3 Remember/Understand questions (levels 1-2)
   - **Round 2**: 2-3 Apply/Analyze questions (levels 3-4)
   - **Round 3**: 1-2 Evaluate/Create questions (levels 5-6)

4. For each question:
   - Present via `AskUserQuestion` with free-text input
   - Evaluate the answer
   - Provide corrective feedback (affirm correct parts, gently correct gaps, reference paper)
   - Track: correct/incorrect/partial

5. **Adaptive difficulty**: If user scores <50% at any level, add 2 more questions at that level before progressing

6. **Quiz summary**: Present score breakdown by Bloom's level:
   ```
   Remember:    2/2 ██████████ 100%
   Understand:  2/3 ██████░░░░  67%
   Apply:       1/2 █████░░░░░  50%
   Analyze:     1/2 █████░░░░░  50%
   Evaluate:    1/1 ██████████ 100%
   Create:      0/1 ░░░░░░░░░░   0%
   Overall:     7/11 (64%)
   ```

7. **Save state**: Write `papers/<slug>/stage2-quiz.json`:
   ```json
   {
     "total_asked": 11,
     "total_correct": 7,
     "by_level": {
       "remember": [2, 2],
       "understand": [3, 2],
       "apply": [2, 1],
       "analyze": [2, 1],
       "evaluate": [1, 1],
       "create": [1, 0]
     },
     "questions": [{"level": "...", "question": "...", "answer": "...", "correct": true, "feedback": "..."}]
   }
   ```

## Stage 3: Next Steps

**Goal**: Extract citations, identify follow-up reading, create action items, write review summary.

### Citation extraction and resolution
1. Find the PDF path: `ls /Users/titus/pyg/paper-review/papers/<slug>/*.pdf`
2. Run citation extraction:
   ```
   uv run --python 3.12 --with PyMuPDF ${CLAUDE_PLUGIN_ROOT}/scripts/extract_citations.py <pdf-path>
   ```
3. Parse the citation JSON output
4. Cross-reference with highlights — prioritize resolving citations that appeared in highlighted text
5. For each prioritized citation, resolve metadata:
   ```
   uv run --python 3.12 --with httpx ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_citation.py --doi <doi>
   ```
   or `--arxiv <id>` or `--title "<title>"`
6. Present resolved citations with title, authors, year, and abstract snippet

### Add papers to reMarkable
7. Ask the user which citations to add to their reading list via `AskUserQuestion`
8. For selected papers with available PDFs (arXiv papers):
   - Download: `curl -L -o /Users/titus/pyg/paper-review/papers/<new-slug>.pdf "https://arxiv.org/pdf/<arxiv_id>"`
   - Upload: `rmapi put /Users/titus/pyg/paper-review/papers/<new-slug>.pdf "To Quiz/"`
9. Add all selected papers to database.json with `status: "to_read"` and `source_paper_id` pointing to current paper

### Action items
10. Ask the user if they have any action items from this paper via `AskUserQuestion`
11. For each action item, create a GitHub issue:
    ```
    gh issue create --repo tbuckworth/tasks --title "<action>" --label "action:look-into" --body "From review of: <paper-title>\n\nContext: <relevant highlight or discussion>"
    ```

### Write review summary
12. Write `/Users/titus/pyg/paper-review/reviews/YYYY-MM-DD-<slug>.md`:
    ```markdown
    # <Paper Title>

    **Authors**: ...
    **Date reviewed**: YYYY-MM-DD
    **Source**: reMarkable / URL

    ## Key Highlights
    - (grouped by theme, not just listed by page)

    ## Key Insights
    - (distilled from quiz performance and discussion)

    ## Quiz Results
    Overall: X/Y (Z%)
    (breakdown by level)

    ## Questions & Answers
    - (from Stage 1)

    ## Follow-up Reading
    - [ ] Paper Title (arXiv:XXXX.XXXXX) — added to reMarkable
    - [ ] Paper Title (DOI:...) — added to database

    ## Action Items
    - [ ] GitHub Issue #N: description
    ```

### Update database
13. Read `/Users/titus/pyg/paper-review/database.json`
14. Create or update the paper entry with all metadata, quiz results, review date
15. Compute `next_review`:
    - Quiz score ≥70%: advance `review_interval_index` by 1
    - Quiz score <50%: reset `review_interval_index` to 0
    - Between 50-70%: keep current index
    - `next_review` = today + schedule[review_interval_index]
16. Write updated database.json

### Archive on reMarkable
17. If the paper was sourced from "To Quiz", archive it:
    ```
    rmapi mv "To Quiz/<name>" "Archive/"
    ```
    If Archive doesn't exist, create it: `rmapi mkdir Archive`

### Spaced repetition reminder
18. Check database.json for other papers where `next_review` ≤ today
19. If any are due, mention them: "You also have N papers due for re-review: ..."

### Cleanup
20. Remove intermediate files: `review-state.json`, `stage1-notes.json`, `stage2-quiz.json` from `papers/<slug>/`

### Git commit
21. Stage and commit review files:
    ```
    cd /Users/titus/pyg/paper-review && git add reviews/ database.json && git commit -m "Review: <paper-title>"
    ```

## For URL-sourced content (no PDF)

When reviewing a blog post or web article (URL source):
- Skip annotation extraction — work directly from web content
- Skip citation extraction script — instead, extract links from the web content itself
- Skip reMarkable archive step
- All other stages work the same: Feynman technique, quiz, action items, review summary
