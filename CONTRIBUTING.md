# Contributing

Contributions are welcome — especially field reports and new patterns.

## Ground rules

1. **No secrets, ever.** Run `bash scripts/check-secrets.sh` before committing.
   No SIDs, tokens, `.env` values, instance hostnames of real customers, or
   dataset/card IDs that belong to someone else's instance.
2. **Keep the evidence tiers honest.** Skill files mark claims as `[DOC]`
   (documented by Domo), `[KB]` (knowledge base), `[REPO]` (verified in running
   code), or `[INFER]` (inferred). Don't upgrade a tier without the evidence.
3. **Fix a skill when you learn something.** These files are field notes; if
   Domo behavior surprised you, that surprise belongs in the skill.

## Where things live

- `skills/` — one file per Domo surface or agent workflow; add an entry to
  `skills/README.md` when adding one
- `docs/` — guides and API references (English files have a `.ja.md` twin)
- `scripts/` — runnable helpers; keep them dependency-light (stdlib + Domo CLI)
- `templates/` — starter skeletons
- `prompts/` — request templates for handing work to an AI agent
- `reference-architectures/` — complete apps; each is self-contained with its
  own README and tests

## Checks

CI runs on every push/PR: secret scan, Markdown link check, JSON/JS syntax,
and the offline test suites of both reference apps. You can run the same
locally:

```bash
python -m pip install pytest -r reference-architectures/inventory-management-app/tests/requirements.txt
bash scripts/check-secrets.sh
python3 scripts/check-public-distribution.py
python3 scripts/check-links.py
python -m pytest --import-mode=importlib reference-architectures/pl-summary-app/tests reference-architectures/inventory-management-app/tests -q
```

## Note for maintainers

The canonical source of `skills/`, `docs/`, `scripts/`, `templates/`, and
`reference-architectures/` is the authors' internal workspace; a sync tool
regenerates and sanitizes them. If you edit those files here directly, your
change may be overwritten by the next sync — prefer opening an issue or PR
describing the change so it can be applied at the source.
