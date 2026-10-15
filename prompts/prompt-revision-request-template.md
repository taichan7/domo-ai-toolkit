# Prompt Revision Request

## Must Read

- `README.md`
- `AGENTS.md`
- `skills/ai-agent-prompt-review.md`
- Relevant Code Engine files and manifests
- Current prompt file

## Prompt To Revise

Path or pasted prompt.

## Goal

Describe what the prompt should improve.

## Constraints

- Function names must match deployed or source-controlled Code Engine functions.
- Output JSON keys, types, enum values, and required fields must be fixed.
- Do not invent Domo assets or function names.
- Do not weaken hard safety blocks without explicit approval.
- Keep time-zone and execution-window rules explicit.
- Keep AppDB save rules aligned with schema and consumers.

## Required Output

- Summary of prompt changes.
- Contract checks performed.
- Remaining ambiguities.
- Validation plan.
