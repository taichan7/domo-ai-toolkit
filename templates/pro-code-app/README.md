# Pro Code Starter App

> 🇯🇵 **日本語版 → [README.ja.md](README.ja.md)**

A minimal Domo Pro Code app skeleton. It loads a dataset bound through the manifest, shows a preview table, and demonstrates the design system this repo recommends.

Use this as the starting point for any custom app. Have an AI agent build your real workflow on top of it. The agent should follow `../../../AGENTS.md` (use the design system variables, use the manifest binding pattern, never call APIs from outside the SDK).

---

## What's in here

| File | Purpose |
|---|---|
| `manifest.json` | Tells Domo about the app: name, size, datasets to bind |
| `index.html` | Structure only — header, stats bar, table card, actions card |
| `styles.css` | All styling, including the design system CSS variables at the top |
| `app.js` | Reads the bound dataset and renders the preview table |

---

## Run it locally

You cannot fully run a Pro Code app outside Domo (the iframe SDK is what gives it data). But you **can** preview the design by opening `index.html` directly:

```bash
# macOS
open index.html

# Linux
xdg-open index.html

# Windows
start index.html
```

The app will show placeholder data and the design system will render correctly.

---

## Wire it to a real dataset

1. In your Domo instance, find a dataset you have access to. Copy its UUID.
2. Open `manifest.json` and replace `REPLACE_WITH_DATASET_UUID` with the real dataset ID.
3. Publish the app:

   ```bash
   # If you have the Domo CLI installed
   domo publish
   ```

4. Open the app in Domo. It will load the first 50 rows of your dataset.

---

## Build on top of it with an AI agent

Once the skeleton is wired to a real dataset, ask your AI agent something like:

> "Add a sage-green primary action button at the top of the actions card that, when clicked, runs `SELECT status, COUNT(*) FROM table GROUP BY status` and renders the result as a bar chart in a new card next to the table."

Because the agent has already read `../../../AGENTS.md` and `../../docs/api-reference.md`, it will:

- Use the design system variables (`--sage-green`, `--sandstone`, etc.) — not hardcoded colors
- Use the manifest binding (`mainDs` alias), not a raw dataset ID in the URL
- Call `domo.post('/sql/v1/mainDs', sql, {contentType: 'text/plain'})`, not a fetch with manual headers
- Respect the grid layout — the new card goes in a real grid cell, not absolute-positioned

---

## Design system cheat sheet

All colors and spacing are CSS variables defined at the top of `styles.css`. Reuse them:

| Variable | When to use |
|---|---|
| `--sage-green` | Positive actions, success states, primary buttons |
| `--canyon-red` | Errors, warnings, destructive actions |
| `--sandstone` | Highlights, secondary actions, accent text |
| `--alpine-blue` | Info, links, neutral data |
| `--snow-white` | Primary text |
| `--text-muted` | Secondary text, labels |
| `--glass-bg` | Card backgrounds |
| `--glass-border` | Card borders, dividers |
| `--gap` | Standard spacing between grid items |

If you find yourself reaching for a new color, ask: does one of the existing ones cover this? Almost always, yes.
