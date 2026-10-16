# Domo App Broadcasting

Use this when you are reasoning about or building **real-time messaging between Custom Apps on the same Domo page** — Domo's App-Framework **App Broadcasting** pub/sub bus (`domo.broadcast()` / `domo.onBroadcast()`), the broadcast `channels` you declare in `manifest.json`, or when you have to tell this apart from the older `sendAppData`/`requestAppDataUpdate` custom-app channel, page filters, and page Variables.

**This is not a green field — it is the newer generation of a surface the repo already documents.** App Broadcasting is the **channel-based, source-identified successor** to the SAME host-mediated custom-app↔custom-app coordination already charted in `domo-procode-embedded-cards.md:101-111` and `:140-143`. That skill's four-channel table (`:106-111`) already names the **older** generation on its **"Custom App Data"** row (`:110` — `sendAppData`/`onAppData` → `requestAppDataUpdate`/`onAppDataUpdated`, *"custom-app ↔ custom-app only"*), and Domo's own broadcasting guide positions `requestAppDataUpdate` as the *"simple one-way notifications — no channels; no source identity"* predecessor that App Broadcasting supersedes `[DOC]`. The **mechanism is unchanged**: every message still travels **iframe → host → iframe** ("sibling cards cannot talk directly", `domo-procode-embedded-cards.md:101-104`). What is genuinely new is layered on top of that transport: **named channels**, a **declared manifest contract** (`channels.publishes`/`channels.subscribes`), **host-stamped source identity** (`sourceAppId`, unspoofable), and a **helper family** (`onBroadcastFrom` / `onBroadcastOnce`). So this skill adds the App Broadcasting **API contract**; it does **not** re-teach the host-mediation transport (owned by `domo-procode-embedded-cards.md`) or the filter/Variable coordination paths (owned by `domo-variables-filters.md`).

## What this skill owns (and what it defers)

**Owns:**
1. The **App Broadcasting runtime API** — `domo.broadcast()`, `domo.onBroadcast()`, `domo.onBroadcastFrom()`, `domo.onBroadcastOnce()`, and the `BroadcastMessage` shape.
2. The **manifest `channels` contract** — `publishes` / `subscribes` and the production subscribe-gating rule.
3. The **host-enforced limits, error codes, feature switch, and `sourceAppId` trust model**, plus the documented **sync-on-mount** workaround for the historyless bus.

**Defers (do not restate their contracts here — cross-reference):**

| Face | Owner |
|---|---|
| Host-mediation transport / iframe-sandbox / the four sanctioned coordination channels (incl. the older `sendAppData`/`requestAppDataUpdate`) | `domo-procode-embedded-cards.md` |
| Page **filter** propagation to standard cards / into an embedded app; page **Variable** value drive (`onVariablesUpdated`/`requestVariablesUpdate`) | `domo-variables-filters.md` |
| `manifest.json` mappings/versioning, `domo publish`, `da new` scaffolding | `domo-procode-app.md` |
| App Studio page as the container that co-locates the app cards | `domo-appstudio.md` |
| Durable / cross-session state (AppDB, dataset) | `domo-code-engine.md` / `domo-datasets.md` |

## Evidence tiers

```
[DOC]   developer.domo.com / www.domo.com/docs App-Framework guides + tutorials:
        the "App Broadcasting" guide and the "Cross-App Broadcasting" React tutorial,
        and the domo-js (ryuu.js) SDK reference they point to.
        NOTE: a domo.com/docs/s/article/<12-digit-id> page is a Salesforce KB help
        article = [KB], NOT [DOC], even though it lives on the docs domain.
[KB]    Domo Knowledge Base / help articles / documented product behavior.
[REPO]  Verified only against THIS repo's working code (re-verify per instance/SDK version).
[INFER] Reasoned from the documented model / community / marketing / inference-from-absence.
```

On disagreement, choose the **more conservative** tier. **A fetch FAILURE (404 / JS-gated) is MISSING evidence, not proof of absence** — never read a failed fetch as confirming a negative.

## The API `[DOC]`

Import is the repo's ordinary idiom — `import domo from 'ryuu.js';` `[REPO]` (16 repo files reference ryuu). **Four methods**, all documented in the guide + tutorial (verbatim signatures):

| Method | Returns | Notes |
|---|---|---|
| `domo.broadcast(channel, payload)` | `void` — **never throws** | Publish `payload` to `channel`. Rejections surface only as a console warning (see Error handling). |
| `domo.onBroadcast(channel, callback)` | an **unsubscribe function** | Subscribe; `callback(msg)` fires per delivery. Call the returned fn to remove the subscription. |
| `domo.onBroadcastFrom(channel, sourceAppId, callback)` | an **unsubscribe function** | Like `onBroadcast`, but only delivers messages from one specific app instance. |
| `domo.onBroadcastOnce(channel, callback)` | (auto-unsubscribes) | Delivers the first matching message, then unsubscribes itself (e.g. one-time config from a coordinator app). |

Each delivered message is a `BroadcastMessage` `[DOC]`:

```typescript
interface BroadcastMessage {
  channel: string;     // channel the message was published to
  payload: unknown;    // data sent by the publisher (parse/cast defensively — it is `unknown`)
  sourceAppId: string; // ID of the app INSTANCE that published it (host-assigned)
  timestamp: number;   // when the host delivered it (ms since epoch, host-assigned)
}
```

React/effect cleanup idiom `[DOC]` — call the unsubscribe fn on unmount so a re-mount does not stack subscriptions:

```javascript
useEffect(() => {
  const unsubscribe = domo.onBroadcast('selection:changed', (msg) => setState(msg.payload));
  return () => unsubscribe();
}, []);
```

TS consumers import the type: `import type { BroadcastMessage } from 'ryuu.js';` `[DOC]`.

## Channels and the manifest contract `[DOC]`

A **channel** is a literal string, compared exactly. Convention is `namespace:event` (`filter:region`, `chart:hover`, `config:theme`, `selection:changed`). Apps declare channels in `manifest.json`:

```json
{
  "channels": {
    "publishes":  [{ "name": "selection:changed", "description": "Fires when the user selects a row" }],
    "subscribes": [{ "name": "filter:region",     "description": "Applies a region filter" }]
  }
}
```

**The declaration does real work — this is the load-bearing rule:** *"in production, an app receives a channel only if that channel is listed under `subscribes`."* `[DOC]` The host wires each app to its declared `subscribes` channels when the app loads. If a subscriber's callback silently never fires in production, **the missing `subscribes` entry is the first suspect** (it may still work in a dev harness — verify against the production gating). `publishes` documents intent; the subscribe list is what gates delivery.

## How it works — five properties `[DOC]`

- **Host-mediated** — every message routes iframe → host → iframe; apps never see each other's iframes or `postMessage` traffic. (Same transport as `domo-procode-embedded-cards.md:101-104`.)
- **One bus per page** — a single bus is shared by all app cards on the page and is **destroyed on navigation**. No persistence, no cross-page messaging.
- **Broker only** — the host validates the channel, stamps sender + timestamp, enforces limits, and routes. It **does not transform your payload**.
- **Fire-and-forget** — **the bus holds no history.** It delivers only to apps subscribed *at that moment*. An app that subscribes later sees only messages published after it joins. (There is **no** replay / sticky / "broadcast last value" mechanism — if you have seen a claim of one, it contradicts this source; teach the sync-on-mount workaround below instead.)
- **No echo** — a publisher never receives its own message, even if subscribed to the same channel.

## `sourceAppId` trust model `[DOC]`

`sourceAppId` identifies the **card instance** that published the message. **The host assigns it — an app cannot set or fake it** — so subscribers can trust it as an authenticity signal. Two copies of the same app on one page have **different** `sourceAppId` values. Use `domo.onBroadcastFrom(channel, sourceAppId, cb)` to listen to exactly one instance when a page has several publishers of the same channel. There is no documented directory of instance IDs yet (a visual inspector is "on the roadmap"); the documented way to discover an ID during development is to **log `sourceAppId`** off a received message `[DOC]`.

## Limits and safety `[DOC]`

The host enforces these on every message, in every environment:

| Rule | Detail |
|---|---|
| Reserved namespace | Channels starting with `domo:` are rejected **(case-insensitive), on both publish and subscribe.** |
| Source identity | The host stamps each message with the sender's `sourceAppId`; it cannot be spoofed. |
| Rate limit | **100 messages/second, per app.** The bus **drops** messages beyond the limit — throttle high-frequency events (e.g. hover) before broadcasting. |
| Payload size | **64 KB per message when serialized.** Larger **or non-serializable** payloads are rejected. |
| Page isolation | The bus lives only for the current page; navigating away clears every subscription. Nothing persists or crosses pages. |

## Error handling — silent by design `[DOC]`

`domo.broadcast()` returns immediately and **never throws** and **never rejects a promise**. When the host rejects a publish it notifies **only the sending app** and the SDK writes a **browser-console warning** — there is nothing to `catch`. Example:

```
[domo.broadcast] PAYLOAD_TOO_LARGE — Payload size 91234 bytes exceeds limit of 65536 bytes (channel: data:export)
```

| Code | Meaning |
|---|---|
| `RESERVED_NAMESPACE` | Channel starts with `domo:` |
| `PAYLOAD_TOO_LARGE` | Serialized payload exceeds 64 KB |
| `PAYLOAD_NOT_SERIALIZABLE` | Payload can't be serialized (e.g. a circular reference) |
| `RATE_LIMIT_EXCEEDED` | More than 100 messages in one second |
| `FEATURE_DISABLED` | The `app-broadcasting` feature switch is off |

**Design consequence:** because failures are console-only, a broadcast that "does nothing" is not observably distinguishable from success at the call site. **Watch the console during development**, keep payloads well under 64 KB, and throttle publishers. This closed list of 5 codes is what the guide documents; treat it as **not proven exhaustive** `[INFER]`.

## Feature switch `[DOC]`

App Broadcasting requires the **`app-broadcasting` feature switch**. **While it is off, publishing is a no-op and no messages are delivered** — the host answers each publish with a `FEATURE_DISABLED` console notice. Enabling it is an admin action. Do not assume it is on: a whole coordination flow can be silently dead on an instance where the switch is off, with only console warnings to show for it. (Whether it is on for any given instance is `[INFER]` here — verify per instance.)

## Sync current state on mount `[DOC]`

Because the bus keeps no history, an app that mounts *after* a value was published starts empty. The **documented workaround** (not a bus feature) is request/republish: the newcomer subscribes, then asks; the state owner answers by republishing. This needs a **second channel** (e.g. `selection:request`), declared `publishes` on the newcomer and `subscribes` on the owner:

```javascript
// Newcomer: subscribe, then request the current value
domo.onBroadcast('selection:changed', (msg) => render(msg.payload));
domo.broadcast('selection:request', {});

// State owner: answer requests by republishing the latest value
let current = null;
domo.onBroadcast('selection:request', () => { if (current) domo.broadcast('selection:changed', current); });
```

This is the ONLY documented late-subscriber catch-up. Do **not** substitute an imagined replay/sticky API — the bus is fire-and-forget.

## When to use broadcasting vs filters/variables `[DOC]`

Choose broadcasting for **free-form, real-time, channel-based coordination within one page** — multiple independent channels, source identity, and a declared manifest contract. It is the wrong tool for **state that must survive navigation**: page **Variables** (shared scalar state, always-current replay) and page **filters** (shared filter state, current-state replay) persist with the page and DO replay to late subscribers — broadcasting does neither. (Variables/filters are owned by `domo-variables-filters.md`; the older no-channel `requestAppDataUpdate` custom-app channel by `domo-procode-embedded-cards.md`.)

| | App Broadcasting | Page Variables | Page Filters |
|---|---|---|---|
| Data shape | any serializable value ≤ 64 KB | primitive values | filter objects |
| Persistence | current page only | saved with the page | saved with the page |
| Late-subscriber replay | **No** (fire-and-forget) | Yes | Yes |
| Multiple channels | Yes (unlimited) | named variables | single filter set |
| Source identity | **Yes** (`sourceAppId`) | No | No |
| Cross-page | No | Yes | Yes |

## Repo precedent — what is `[REPO]` (and the SDK-version guard)

- **The import idiom is real** `[REPO]`: `import domo from 'ryuu.js'` is how the repo's Pro Code apps load the SDK (16 files reference ryuu).
- **App Broadcasting is ABSENT from the repo's pinned SDK** `[REPO]`: the vendored `ryuu.js` build is **4.6.0**, byte-identical across all vendored copies (`md5 77b232e5…`, per `domo-variables-filters.md:170`), and its listener registry is exactly `{onFiltersUpdate, onAppData, onVariablesUpdated}` — **there is no `broadcast`/`onBroadcast`** in it. So **broadcasting cannot run against the SDK the repo currently vendors**; it requires the **v5/v6 generation** (the same generation gap flagged at `domo-procode-embedded-cards.md:140-143`). Which exact SDK version first shipped broadcasting is `[INFER]` — pin and feature-detect before relying on it.
- **Zero App-Framework broadcasting usage exists repo-wide** `[REPO]`: the only two `broadcast` tokens in the tree are **false friends** — a CodeEngine SMS helper `broadcast_text_message()` and a Magic ETL "global-broadcast join" (a data-fanout sense, `2026-09-04-df3063-…:88`). Neither is the pub/sub bus.
- Therefore **every runtime-contract claim here is `[DOC]`**, anchored only to the two dev-portal guides — **never `[REPO]`**, because no repo code exercises the API. Re-verify live before asserting behavior on any instance.

## Naming traps

- **App Broadcasting ≠ the older `sendAppData`/`requestAppDataUpdate` "Custom App Data" channel** (`domo-procode-embedded-cards.md:110`). Same host-mediated custom-app↔custom-app transport, **older generation**: no named channels, no `sourceAppId`. App Broadcasting is the successor, not a parallel option.
- **App Broadcasting ≠ page filters / page Variables** — those persist and replay; broadcasting does not (table above). → `domo-variables-filters.md`.
- **`broadcast()` (App-Framework pub/sub) ≠ `broadcast_text_message()`** (a CodeEngine SMS/notification function) **≠ a Magic ETL "broadcast join"** (fanning a scalar to all rows). Three unrelated senses of "broadcast" — do not cross-wire.
- **`sourceAppId` ≠ a manifest/app id you set** — it is the host-assigned per-**instance** id; two copies of one app differ. You cannot fake it or read it before receiving a message.

## Safety

App Broadcasting is a **client-side, page-scoped, in-browser bus** — there is no server mutation, no export, and nothing to gate for *documentation* work. Two cautions when building on it: (a) `payload` is delivered to every subscribing app card on the page — **do not broadcast secrets or PII** (any co-located card can subscribe; the 64 KB ceiling is about size, not confidentiality); (b) `sourceAppId` is trustworthy for *authenticity* (host-assigned, unspoofable) but the **payload is not validated** by the host — a subscriber must still treat `msg.payload` as untrusted input and parse defensively. Deploying an app that uses broadcasting is a `domo publish` (human-gated per the standing deployment rules) → `domo-procode-app.md`.
