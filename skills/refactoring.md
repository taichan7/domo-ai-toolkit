# Refactoring Skill

Use this when improving structure, names, duplication, or maintainability without intending behavior changes.

## Rules

- Preserve behavior unless the user explicitly asks for a behavior change.
- Preserve public function names, signatures, return shapes, manifest aliases, Domo object names, and external contracts.
- Avoid large renames or file moves unless the references are clear and validation can prove they are safe.
- Keep refactors small enough to review and roll back.
- Separate mechanical formatting from logic changes when practical.
- Update README, docs, or handoff notes when the structure changes.

## Before Editing

- Identify callers and consumers with `rg`.
- Read the project README, manifest, entrypoint, and relevant prompt/workflow files.
- Note any assumptions about Domo assets that cannot be verified locally.

## Validation

- Run the same tests that would have covered the pre-refactor behavior.
- For Pro Code apps, validate `manifest.json` and JavaScript syntax.
- For Code Engine functions, compile Python where applicable and inspect exported JS functions.
- Record exact checks and remaining risk in the handoff.
