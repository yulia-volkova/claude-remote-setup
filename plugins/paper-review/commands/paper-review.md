---
description: Interactive paper review with annotation extraction, Bloom's taxonomy quiz, and spaced repetition
argument-hint: "[document-name-or-URL]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, AskUserQuestion]
model: claude-opus-4-6
---

# Paper Review Orchestrator

You run an interactive 5-stage paper review: **Understand -> Quiz -> Wrap Up -> Spaced Repetition -> Plan Tomorrow**. You manage the entire flow, using `AskUserQuestion` for all user interaction.

## Constants

- **Data repo**: `/Users/yuliav/study-notes`
- **Plugin root**: `${CLAUDE_PLUGIN_ROOT}`
- **Scripts run via**: `uv run --python 3.12 --with <deps> ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py`
- **Apollo Interview Prep folder**: `Apollo Interview Prep/Done` on reMarkable — equivalent to `To Quiz`

## State Recovery

After each stage, write intermediate results to `papers/<slug>/` so later stages don't depend on context window. If you lose context, check for:
- `papers/<slug>/review-state.json` — overall state (current stage, slug, source)
- `papers/<slug>/stage1-notes.json` — Stage 1 output
- `papers/<slug>/stage2-quiz.json` — Stage 2 output

## Startup: Acquire the Paper

Parse `{{argument}}`:

### No argument
1. Check `reading-list.md` in the data repo for the next unread paper in the current week's schedule.
2. Present the suggestion via `AskUserQuestion` -- let the user confirm or pick a different one.

### URL (starts with `http`)
1. Use `WebFetch` to get the content
2. Generate a slug from the page title
3. Create `mkdir -p /Users/yuliav/study-notes/papers/<slug>`
4. Save the web content -- no PDF extraction needed, work from web content directly
5. Skip to Stage 1 with the web content as the source material

### Local PDF path (Notability export)
1. Generate slug from the PDF filename: lowercase, hyphenated, max 50 chars (e.g., `ai-control-improving-safety`)
2. `mkdir -p /Users/yuliav/study-notes/papers/<slug>`
3. Copy the PDF: `cp "<path>" /Users/yuliav/study-notes/papers/<slug>/`
4. **Start annotation extraction in background** (saves annotations.json when done):
   ```
   uv run --python 3.12 --with PyMuPDF,Pillow,pyobjc-framework-Vision ${CLAUDE_PLUGIN_ROOT}/scripts/extract_notability_annotations.py /Users/yuliav/study-notes/papers/<slug>/*.pdf > /Users/yuliav/study-notes/papers/<slug>/annotations.json 2>/dev/null
   ```
   Run this with `Bash(run_in_background=true)`.
5. **Extract PDF text in foreground** (fast, ~2s):
   ```
   uv run --python 3.12 --with PyMuPDF python3 -c "import fitz,json,sys;d=fitz.open(sys.argv[1]);print(json.dumps({'pages':[d[i].get_text() for i in range(len(d))],'total':len(d)}));d.close()" /Users/yuliav/study-notes/papers/<slug>/*.pdf
   ```
   Parse the JSON output -- this provides the text needed for Stage 2 (quiz).
6. Save state:
   ```json
   // papers/<slug>/review-state.json
   {"stage": 2, "slug": "<slug>", "source": "notability", "pdf_path": "<path>", "title": "...", "annotations_file": "annotations.json"}
   ```

### Execution Order

Run **Stage 2 (Quiz) first** using the foreground PDF text -- the user starts learning immediately. Then run **Stage 1 (Understanding)** which needs annotations. This reorder means the user isn't waiting for annotation extraction.

At Stage 1 start: check if `papers/<slug>/annotations.json` exists and is non-empty. If not, wait up to 30s checking every 5s.

### Auto-migrate v1 papers
Before proceeding, check `database.json` for any reviewed papers missing SM-2 fields. For each, add defaults:
```json
{
  "easiness_factor": 2.5,
  "interval_days": 0,
  "repetition_number": 0,
  "quality_history": []
}
```

## Stage 1: Understanding & Questions (~5 min)

**Goal**: Help the user understand the paper deeply.

1. **Load annotations**: Read `papers/<slug>/annotations.json`. Wait for it if background extraction is still running.

2. **Present highlights**: Group by theme, show each highlight with its page number and `color_name`.

3. **Transcribe handwritten notes**: For each entry in `handwritten_notes`:
   - If the `transcription` field is non-empty, use it directly (OCR already done)
   - If `transcription` is empty, fall back to using the Read tool to view the `ink_on_white_path` PNG and transcribe visually
   - Use `surrounding_text` for context about what the note refers to
   - Present transcription grouped with nearby highlights

4. **Identify question annotations**: Look for highlights containing "?", "why", "how", "what does", "what is", or other question-like patterns. Present these to the user as their own questions.

5. **Answer questions**: For each question the user raised (via annotations or interactively):
   - First try to answer from the paper content
   - If the paper doesn't fully address it, use `WebSearch` to find answers
   - Cite specific sections/pages when referencing the paper

6. **Feynman Technique**: Pick **3-4** key concepts from the highlights (or from the paper content for URL sources). For each:
   - Ask (via `AskUserQuestion`): "Explain [concept] as if teaching someone who has never encountered it."
   - Evaluate with concise 2-sentence feedback following the corrective feedback patterns from the learning science skill
   - Identify gaps: vague hand-waving, circular definitions, missing mechanisms

7. **Defend Your Position**: After the Feynman explanations, pick the paper's most controversial or load-bearing claim. Present a counterargument and ask (via `AskUserQuestion`): "Here's a counterargument: [counterargument]. How would you respond?" Evaluate the user's defense for logical rigor and evidence use.

8. **Proceed directly to Stage 3** (no "Ready?" prompt).

9. **Save state**: Write `papers/<slug>/stage1-notes.json`:
   ```json
   {
     "questions_asked": [...],
     "feynman_concepts": [{"concept": "...", "user_explanation": "...", "gaps": [...], "feedback": "..."}],
     "key_themes": [...]
   }
   ```

## Stage 2: Quiz — Bloom's Taxonomy (~8 min)

**Goal**: Test comprehension at progressively higher cognitive levels. 6 questions, no adaptive difficulty.

1. Load question stems from `${CLAUDE_PLUGIN_ROOT}/skills/learning-science/references/blooms-taxonomy.md`

2. Use the PDF text extracted in the foreground step. If `papers/<slug>/stage1-notes.json` exists (i.e., Stage 1 ran first for URL sources), use identified themes and gaps to inform question selection.

3. Generate and present **6 questions total**:
   - **2** Remember/Understand questions (levels 1-2)
   - **2** Apply/Analyze questions (levels 3-4)
   - **2** Evaluate/Create questions (levels 5-6)

4. For each question:
   - Present via `AskUserQuestion` with free-text input
   - Evaluate the answer
   - Brief 1-2 sentence corrective feedback (affirm correct parts, gently correct gaps)
   - Track: correct/incorrect/partial
   - **Carry forward**: For questions 2-6, prepend previous question's feedback at the top of the `AskUserQuestion` text: `Previous: [correct/incorrect] — [feedback]\n\nQuestion N/6 ([level]):`

5. **Quiz summary**: Present score breakdown by Bloom's level:
   ```
   Remember:    1/1 ██████████ 100%
   Understand:  1/1 ██████████ 100%
   Apply:       1/1 ██████████ 100%
   Analyze:     0/1 ░░░░░░░░░░   0%
   Evaluate:    1/1 ██████████ 100%
   Create:      0/1 ░░░░░░░░░░   0%
   Overall:     4/6 (67%)
   ```

6. **Save state**: Write `papers/<slug>/stage2-quiz.json`:
   ```json
   {
     "total_asked": 6,
     "total_correct": 4,
     "by_level": {
       "remember": [1, 1],
       "understand": [1, 1],
       "apply": [1, 1],
       "analyze": [1, 0],
       "evaluate": [1, 1],
       "create": [1, 0]
     },
     "questions": [{"level": "...", "question": "...", "answer": "...", "correct": true, "feedback": "..."}]
   }
   ```

## Stage 3: Wrap Up (~3 min)

**Goal**: Resolve citations, write review, update database, archive.

### Citation extraction and resolution
1. Find the PDF path: `ls /Users/yuliav/study-notes/papers/<slug>/*.pdf`
2. Run citation extraction:
   ```
   uv run --python 3.12 --with PyMuPDF ${CLAUDE_PLUGIN_ROOT}/scripts/extract_citations.py <pdf-path>
   ```
3. Parse the citation JSON output
4. Cross-reference with highlights — resolve **top 3-5** citations from highlighted text
5. For each prioritized citation, resolve metadata:
   ```
   uv run --python 3.12 --with httpx ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_citation.py --doi <doi>
   ```
   or `--arxiv <id>` or `--title "<title>"`
6. Present resolved citations and ask in a **single prompt** which to add to reading list

### Queue follow-up papers
7. For selected papers with available PDFs (arXiv papers):
   - Download: `curl -L -o /Users/yuliav/study-notes/papers/<new-slug>.pdf "https://arxiv.org/pdf/<arxiv_id>"`
8. Add all selected papers to database.json with `status: "to_read"` and `source_paper_id` pointing to current paper

### Action items
9. Ask the user if they have any action items from this paper via `AskUserQuestion`
10. For each action item, create a GitHub issue with intelligent labels:

    **Always**: `source:claude`, `section:work`
    **Action** (infer from content):
    - `action:look-into` (default) — research, investigate
    - `action:email` — "reach out to", "contact", "email"
    - `action:call` — "call", "schedule a meeting"
    - `action:manual` — "implement", "code", "build", "write"
    - `action:buy` — "buy", "purchase", "subscribe"
    **List** (infer from content):
    - `list:to-read` — reading items (papers, posts, books)
    - `list:tasks` — general tasks (default)
    - `list:philosophy` — deep questions, worldview considerations
    **Priority**: `priority:medium` (default), `priority:high` if urgent, `priority:low` if "someday"

    ```
    gh issue create --repo yulia-volkova/tasks \
      --title "<action>" \
      --label "source:claude,action:<type>,list:<list>,section:work,priority:<level>" \
      --body "From review of: <paper-title>\n\nContext: <relevant highlight or discussion>"
    ```

### Write review summary
11. Write `/Users/yuliav/study-notes/reviews/YYYY-MM-DD-<slug>.md`:
    ```markdown
    # <Paper Title>

    **Authors**: ...
    **Date reviewed**: YYYY-MM-DD
    **Source**: Notability PDF / URL

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
    - [ ] Paper Title (arXiv:XXXX.XXXXX) — added to database
    - [ ] Paper Title (DOI:...) — added to database

    ## Action Items
    - [ ] GitHub Issue #N: description
    ```

### Update database with SM-2
12. Read `/Users/yuliav/study-notes/database.json`
13. Compute quiz percentage: `pct = total_correct / total_asked * 100`
14. Map to SM-2 quality:
    - 90-100% -> q=5, 70-89% -> q=4, 50-69% -> q=3, 30-49% -> q=2, 10-29% -> q=1, 0-9% -> q=0
15. Update SM-2 state:
    ```
    EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
    EF  = max(EF', 1.3)

    if q >= 3:  # pass
      rep 0 -> interval = 1
      rep 1 -> interval = 6
      rep n -> interval = round(prev_interval * EF)
      repetition_number += 1
    else:        # fail
      repetition_number = 0
      interval = 1

    next_review = today + interval days
    ```
16. Write updated paper entry with: `easiness_factor`, `interval_days`, `repetition_number`, `quality_history` (append q), `next_review`, quiz results, review date
17. Write updated database.json

### Cleanup
18. Remove intermediate files: `review-state.json`, `stage1-notes.json`, `stage2-quiz.json` from `papers/<slug>/`

### Git commit
19. Stage and commit review files:
    ```
    cd /Users/yuliav/study-notes && git add reviews/ database.json && git commit -m "Review: <paper-title>"
    ```

## Stage 4: Spaced Repetition (5-15 min, user-controlled)

**Goal**: Active review of previously studied papers using SM-2 priority queue.

1. Run the SR priority script:
   ```
   uv run --python 3.12 ${CLAUDE_PLUGIN_ROOT}/scripts/sr_priority.py /Users/yuliav/study-notes/database.json
   ```
2. Parse the JSON output — this is the priority queue of papers where `next_review <= today`
3. If empty: "No papers due for review today." -> skip to Stage 5
4. For each paper in priority order:
   a. Show brief context: title, last score, days since review, weak Bloom's levels
   b. Read the paper's review markdown file to refresh context on key insights and weak areas
   c. Ask **3-5 targeted questions** focused on:
      - Weak Bloom's levels from previous quiz (e.g., if analyze was 0%, ask analyze-level questions)
      - Key insights from the review file
      - Connections to other reviewed papers
   d. Each question via `AskUserQuestion` — include "Done for today" as an option. If selected, save progress immediately and jump to Stage 5
   e. **Carry forward**: For each question after the first, include previous feedback at the top of the `AskUserQuestion` text: `Previous: [correct/incorrect] — [feedback]\n\nQuestion N of M:`
   f. After each paper: compute score, map to SM-2 quality, update SM-2 state (same algorithm as Stage 3 step 15-16)
   g. Save to database.json **immediately** (not batched) — append review date, update quality_history, EF, interval, next_review
   h. Mini-summary: `"Paper X: 3/4 (75%) -> quality 4, next review in 6 days"`
5. After all papers reviewed, show session summary:
   ```
   SR Session Complete:
   - Paper A: 4/5 (80%) -> next review Mar 12
   - Paper B: 2/4 (50%) -> next review Mar 7
   ```
6. Git commit SR updates:
   ```
   cd /Users/yuliav/study-notes && git add database.json && git commit -m "SR session: <N> papers reviewed"
   ```

## Stage 5: Plan Tomorrow (~1 min)

1. Read `reading-list.md` from the data repo to find the next unread paper in the current week
2. Read database.json -- check which papers in `to_read` status are cited by multiple reviewed papers
3. Suggest what to read next:
   - First: next item in `reading-list.md` that hasn't been reviewed yet (cross-reference with database.json)
   - Then: papers cited by multiple reviewed papers
   - Then: by time in queue (oldest `date_added` first)
4. Final message: "Session complete. Next SR due: [earliest next_review date from database]. Tomorrow's reading: [suggestion]."

## For URL-sourced content (no PDF)

When reviewing a blog post or web article (URL source):
- Skip annotation extraction -- work directly from web content
- Skip citation extraction script -- instead, extract links from the web content itself
- All other stages work the same: Feynman technique, quiz, action items, review summary
