---
description: Review secure-tunnel research writing for clear, human, public-facing sense without diluting technical truth. Use when Codex needs to simplify wording, reduce hype, improve accessibility, or catch prose that sounds stronger than the evidence.
---

# Public Sense Review

## Purpose
Make technical writing easier to trust and easier to read.

This skill is for prose quality, not evidence generation.

## What To Review
- abstract
- introduction
- system overview
- conclusion
- reviewer responses
- plain-language summaries

## Rules
- Keep the technical meaning intact.
- Replace hype with concrete statements.
- Prefer short, direct sentences.
- Make scope boundaries explicit.
- If the evidence is narrow, say so plainly.

## Do Not Do
- Do not invent simplified explanations that change the protocol or measurement facts.
- Do not turn a code-backed limitation into a vague future-work sentence.
- Do not remove caveats that protect scientific accuracy.

## Workflow
1. Read the section being reviewed.
2. Mark sentences that are too broad, too polished, or unclear.
3. Rewrite for directness and credibility.
4. Keep every quantitative or behavioral claim aligned with the cited evidence.

## Output
Return:
- `original_issue`
- `why_it_feels_wrong`
- `safer_rewrite`
- `evidence_note` if the sentence should be narrowed rather than rewritten
