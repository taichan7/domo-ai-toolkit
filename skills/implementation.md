# Implementation Skill

Use this when changing code, scripts, Pro Code assets, Code Engine functions, prompts, or workflow glue.

## Checklist

- Read `AGENTS.md`, `README.md`, `TOOLS.md` or `tools.json`, `tasks/shared-notices.md`, `tasks/in-progress.md`, relevant handoffs, and the target project README if it exists.
- Read the relevant entrypoint before changing behavior: manifest, app script, Code Engine function, dataflow script, prompt, or workflow JSON.
- Keep the change scoped to the user's request and the smallest practical set of files.
- For a large file (full Pro Code `app.js` / `index.html`, long prompt, big dataflow JSON), write a minimal version with unique placeholders first, then fill it with a few small edits — never one giant single-shot write, which can truncate mid-write and leave the file partial. See `AGENTS.md` → "Writing Large Files". This is separate from the file-count point above: that is about how *many* files you touch; this is about not writing one large file in a single shot.
- Preserve public function names, function signatures, manifest aliases, AppDB names, Dataset names, FileSet names, Workflow names, and external API contracts unless the user explicitly asks for a breaking change.
- State assumptions in the handoff or final report when behavior depends on unverified Domo state.
- Record failed attempts, slow debugging paths, reusable knowledge, and skill candidates in the handoff when the work is non-trivial.
- Prefer existing helpers from `../scripts/`, `../templates/`, and `../skills/` over new one-off scripts.

## Error Handling

- Return explicit success/failure states from Code Engine functions.
- For AI-facing functions, use clear output keys such as `success`, `message`, `status`, `error`, `data`, and `diagnostics`.
- Include timeouts, retries, and structured error messages around external APIs when the existing project pattern supports it.
- Avoid logging secrets, request headers, tokens, cookies, full raw customer payloads, or large documents.

## Compatibility

- Preserve return types and field names that Pro Code apps, workflows, or prompts already consume.
- Do not change `manifest.json` aliases without updating every caller and documenting the migration.
- Keep Domo environment-specific values in manifests or configuration, not scattered through app code.

## Validation Notes

Record the checks run and the checks not run. For narrow Pro Code changes, useful local checks include:

```bash
python3 -m json.tool <project>/pro-code/manifest.json >/dev/null
node --check <project>/pro-code/app.js
```

Always run workspace safety checks before finishing a non-trivial change:

```bash
bash ../scripts/check-secrets.sh
bash ../scripts/validate-workspace.sh
```
