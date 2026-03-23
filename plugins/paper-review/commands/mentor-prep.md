---
description: Prepare for weekly mentor meeting -- guided reflection, agenda drafting, and message to mentor
argument-hint: "[week-number (optional)]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion]
model: claude-opus-4-6
---

# Weekly Mentor Prep

You guide the user through reflecting on their week's study, then help them draft a message to their mentor proposing a meeting agenda. The user does the thinking -- you ask the questions.

## Constants

- **Data repo**: `/Users/yuliav/study-notes`
- **Reviews dir**: `/Users/yuliav/study-notes/reviews/`
- **Database**: `/Users/yuliav/study-notes/database.json`
- **Reading list**: `/Users/yuliav/study-notes/reading-list.md`

## Step 1: Gather the Week's Work

1. Parse `{{argument}}` for a week number (1-4). If none, infer from today's date using the reading list schedule.
2. Read `database.json` and find all papers reviewed this week (by `review_dates`).
3. Read each paper's review file from `reviews/`.
4. Read quiz results -- note weak Bloom's levels across all papers this week.
5. Present a brief summary: "This week you reviewed N papers on [topic]. Here's what I see..."

## Step 2: Guided Reflection (3-4 questions via AskUserQuestion)

Ask these one at a time. Each builds on the previous answer.

**Question 1 -- Confusions**: "What confused you most this week? This could be a concept you can state but don't deeply understand, a claim you're not sure you believe, or something two papers seem to disagree about."

**Question 2 -- Surprises**: "What surprised you or changed your mind? Did any reading shift your priors on timelines, threat models, or control approaches?"

**Question 3 -- Connections**: "Did you notice connections between this week's readings and things you already knew or previously read? Any tensions or reinforcements?"

**Question 4 -- Gaps**: "What do you feel you're still missing? What would help you most -- deeper explanation, a worked example, a debate, seeing how this applies to a real system?"

## Step 3: Identify Discussion Topics

Based on the user's answers and the week's quiz data:
1. Identify 2-4 candidate discussion topics, prioritizing:
   - Genuine confusions (these are gold for mentor time)
   - Disagreements with paper claims (mentor can stress-test reasoning)
   - Weak Bloom's levels (if Analyze/Evaluate were low, the user needs guided practice)
   - Connections the user spotted (mentor can validate or deepen)
2. For each topic, draft a 1-sentence "why this is valuable to discuss" rationale.
3. Present the candidates via `AskUserQuestion` and let the user pick/reorder.

## Step 4: Draft Mentor Message

Write a draft message (casual, professional) with this structure:

```
Hey [mentor],

Here's what I covered this week: [1-2 sentence summary of readings + key themes]

I'd like to propose this agenda for our meeting:

1. [Topic] -- [why it's valuable: e.g., "I'm confused about X and think talking through it would help me distinguish Y from Z"]
2. [Topic] -- [why it's valuable]
3. [Topic] -- [why it's valuable]

Happy to steer the conversation differently if you think there's something more important to hit -- just let me know!

[user name]
```

Present the draft via `AskUserQuestion` for the user to approve or edit.

## Step 5: Save and Commit

1. Write the prep notes to `/Users/yuliav/study-notes/reviews/YYYY-MM-DD-week-N-mentor-prep.md` containing:
   - Week number and dates
   - Papers reviewed (with scores)
   - Reflection answers
   - Proposed agenda with rationale
   - Final mentor message
2. Git commit:
   ```
   cd /Users/yuliav/study-notes && git add reviews/ && git commit -m "Mentor prep: Week N"
   ```
