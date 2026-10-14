# AI Agent Prompt Review Skill

Use this when reviewing prompts used by workflows, Code Engine functions, trading systems, approval systems, or other AI agents.

## Review Checklist

- Public function names match actual Code Engine exports.
- The prompt does not ask the agent to call nonexistent functions.
- Hard Block and Soft Block conditions are distinct and ordered.
- HOLD, STOP, Entry, Exit, and Trail conditions have clear priority.
- Output JSON keys, types, enum values, and required fields are fixed.
- AppDB save rules match actual collection schema and app expectations.
- Dataset, AppDB, FileSet, Workflow, and Code Engine names match manifests or docs.
- Time-zone and trading-hour rules are explicit.
- The prompt balances safety with executable next steps; it should not avoid action through vague HOLD conditions.
- Error handling paths tell the caller what to do next.

## Reporting

Separate:

- Contract mismatches.
- Ambiguous instructions.
- Safety risks.
- Execution blockers.
- Suggested prompt edits.
