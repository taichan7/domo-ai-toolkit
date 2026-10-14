# Domo Auth And Deployment

This workspace uses Domo CLI/API-first workflows. Browser automation is not the default way to operate Domo.

## Auth Priority

Use this order:

1. `INSTANCE` + `DOMO_TOKEN`
2. `INSTANCE` + `SID`
3. `domo login`
4. `bash ../scripts/authenticate.sh <instance>`

Header reference:

| Method | Header |
|---|---|
| Developer token | `X-DOMO-Developer-Token: $DOMO_TOKEN` |
| CLI SID | `X-Domo-Authentication: $SID` |
| Public API OAuth | `Authorization: Bearer $ACCESS_TOKEN` |

## Never Store

Do not store these in git:

- `.env`, `.env.*`
- `.sid`
- `.domo/`
- `*.token`
- `*.pem`, `*.key`
- `sid.txt`
- `access_token.txt`
- refresh tokens
- developer tokens
- workflow admin PATs
- downloaded publish bundles or generated zip files

Run:

```bash
bash ../scripts/check-secrets.sh
```

## Pro Code Deploy

Deploy command:

```bash
cd <project>/pro-code
domo publish
```

Rules:

- Get explicit user confirmation before `domo publish`.
- Confirm the target instance first.
- Preserve `manifest.json` aliases.
- Remove or rewrite stale source instance IDs before publishing a cloned app.
- Do not publish build artifacts into git.

## Code Engine And Workflow Secrets

Secrets belong in Domo-managed configuration, workflow environment variables, or user-provided environment variables. Document secret names, not secret values.

Use README text like:

```md
Required environment variables:

- `DOMO_TOKEN` - Domo developer token with dataset read access.
- `OPENAI_API_KEY` - Set in Domo workflow/Code Engine secrets.
```

## Dataflow Writes

For Magic ETL/dataflow changes:

1. GET the full object.
2. Modify in memory.
3. PUT the full object back.
4. Trigger or run.
5. Verify execution result.

Do not make destructive dataflow changes without confirmation.
