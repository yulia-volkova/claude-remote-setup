---
description: "Learning science techniques for paper review: Bloom's taxonomy question generation, Feynman technique, spaced repetition, and corrective feedback"
---

# Learning Science Techniques for Paper Review

## Bloom's Taxonomy — Progressive Question Generation

Generate questions at progressively higher cognitive levels. Start at Remember/Understand and only progress when the user demonstrates mastery (≥50% correct at each level).

See `${CLAUDE_PLUGIN_ROOT}/skills/learning-science/references/blooms-taxonomy.md` for question stem templates at each level.

### Difficulty Calibration
- Start at Remember/Understand (levels 1-2)
- Progress only when user scores ≥50% at current level
- If user scores <50%, add 2 more questions at that level before trying to progress
- Optimal difficulty is ~50% — prevents boredom (too easy) and frustration (too hard)

## Feynman Technique

1. Pick 2-3 key concepts from the paper's highlights
2. Ask the user: "Explain [concept] as if teaching someone who has never encountered it"
3. Listen for:
   - Vague hand-waving ("it basically just...")
   - Circular definitions (using the term to define itself)
   - Missing mechanism (what, but not how or why)
4. Provide corrective feedback:
   - Affirm what they got right: "You correctly identified that..."
   - Gently point to gaps: "One thing to consider is..."
   - Reference the paper: "The authors specifically address this on page X where they say..."

## Spaced Repetition

Schedule intervals: **[1, 3, 7, 14, 30, 90]** days

- `review_interval_index` tracks position in the schedule
- After successful review (quiz score ≥70%): advance to next interval
- After poor review (quiz score <50%): reset to interval 0
- Between 50-70%: stay at current interval
- `next_review` = last review date + schedule[review_interval_index]

## Corrective Feedback Patterns

After each quiz answer:

### Correct answer
- Brief affirmation: "Exactly right."
- Optionally add depth: "And to build on that, the paper also notes..."

### Partially correct
- Affirm correct parts: "You're right that [X]."
- Fill gaps: "However, the paper also emphasizes [Y], which is important because..."

### Incorrect
- Don't say "wrong" — say "Not quite" or "Let me clarify"
- Explain the correct answer with reference to specific paper content
- If the misconception is common, briefly explain why it's a natural mistake

## Progressive Summarization (Forte)

The 4-layer distillation happens naturally across the review:
1. **Layer 1**: Full paper text (the PDF itself)
2. **Layer 2**: Highlights from reMarkable (what caught the reader's eye)
3. **Layer 3**: Quiz results and Feynman explanations (tested understanding)
4. **Layer 4**: Key insights in the review summary (distilled knowledge)
