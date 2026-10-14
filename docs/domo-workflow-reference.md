# Domo Workflows — Feature Reference

> Companion to the [`domo-workflow` skill](../skills/domo-workflow.md). Per-shape / per-action reference
> compiled from Domo product documentation and community sources (cited per feature) plus live v2
> authoring verification on `maintenance-instance` (2026-09-05).

**Architecture note that saves hours:** most 'Domo actions' in Workflows are NOT dedicated node types —
they are **Code Engine packages** surfaced as automated-task steps. Only a handful of shapes are truly
native (Start, End, gateways, Wait, Timer, User Task/Email, Sub Flow, AI Agent). Everything else
(DataSet CRUD, run a DataFlow, AppDB CRUD, Buzz, Slack/Teams, card/page/user management) is a function
call into a Code Engine package. See the skill for how this changes authoring.

## Contents

- [Control flow (gateways, timers, sub-flows, expressions)](#control-flow-gateways-timers-sub-flows-expressions)
- [Triggers & entry points](#triggers--entry-points)
- [Action steps (Domo actions & Code Engine functions)](#action-steps-domo-actions--code-engine-functions)

## Control flow (gateways, timers, sub-flows, expressions)

### branching

#### Conditional Logic (Exclusive Gateway)
*Category: branching*

- **What it does:** A decision/branch shape that evaluates if/then conditions on each outgoing flow and routes execution down exactly ONE path. At runtime the workflow travels down the first outgoing flow whose condition evaluates true. Only one outgoing flow may fire from a conditional shape.
- **When to use:** When the workflow must choose a single path based on variable values (approve vs reject, priority routing, threshold checks). This is the XOR/exclusive-gateway pattern.
- **API / JSON representation:** Conceptually a BPMN exclusive gateway (XOR) with FEEL condition expressions on sequence flows (Domo Workflows is built on a Camunda/Zeebe-style engine — FEEL is the tell). Domo does not publicly expose the model JSON/type string; not settable via the public REST API.
- **Config options:** Add via 'Add a new shape > Flow Controls > Conditional Logic'. Name the shape. Use the shape's node ports to draw multiple outgoing flows, then configure each flow's condition. Per-condition you set a Name, Description, and a Configuration type: (1) Default — the fallback path taken only if no other condition is true; (2) Basic — general expression editor: pick a variable via the 'Datalist variable' dropdown, choose a Comparison value type (custom value, null value, or another variable), then 'Add Rule'; rules in one group are AND-ed, new groups are OR-ed; (3) Advanced — enter FEEL syntax expression, required for referencing Open/Defined Object variables at the parent level or operations unavailable in Basic; variables can be inserted into the expression.
- **Gotchas:** STRONGLY recommended (though not required) to configure a Default condition: because only one outgoing flow can fire, if NO condition evaluates true the workflow ERRORS and FAILS. FEEL context braces {} differ from grouping parentheses (). Basic config cannot reference whole objects at parent level — use Advanced/FEEL for that.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

#### Parallel Logic (Parallel Gateway)
*Category: branching*

- **What it does:** A gateway shape that forces the workflow to branch into multiple outgoing flows that are ALL active at the same time (concurrent execution). Used both to fork (split into parallel branches) and, when multiple flows converge on a parallel shape, to join/synchronize.
- **When to use:** When several independent steps should run simultaneously (e.g., notify multiple teams, run parallel API calls) and/or when you must wait for all parallel branches to finish before proceeding.
- **API / JSON representation:** Conceptually a BPMN parallel gateway (AND-split / AND-join). Not exposed via public API.
- **Config options:** Add via 'Flow Controls > Parallel Logic'. Name the shape. Draw multiple outgoing flows; if two outgoing flows already exist, use the 'Add Gateway' option in the corner of the shape to add more. No per-flow condition is needed (all branches run). For synchronization, route multiple incoming flows into a parallel shape.
- **Gotchas:** Convergence is a barrier: 'it waits for ALL incoming flows to reach that shape before moving forward.' If one branch never arrives, the join blocks. Contrast with Conditional Logic where only one branch is taken.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

### timing

#### Wait shape
*Category: timing*

- **What it does:** A Flow Control shape that delays/pauses workflow execution before continuing to the next shape.
- **When to use:** To insert a deliberate delay (e.g., wait N minutes/hours before a follow-up step, throttle between API calls, pause before re-checking a condition).
- **API / JSON representation:** Conceptually a BPMN intermediate timer catch event (timer duration). Not exposed via public API.
- **Config options:** Add via 'Flow Controls > Wait'. Delay is expressed using the Duration data type — map a Duration variable or enter a custom duration value. (During execution, Wait shapes put the instance into Recovery-eligible 'in progress' state.)
- **Gotchas:** A workflow paused on a Wait shape shows as In Progress and is visible in Recovery mode; the Reference article does not explicitly document absolute-date waits vs relative durations — treat it as a duration-based delay. Long waits keep an execution open (best practice to cancel stuck In-Progress executions so logs stay clean).
- **Sources:** https://www.domo.com/docs/s/article/000005331, https://www.domo.com/docs/s/article/000005179

#### Timer Events (interrupting / non-interrupting boundary timers)
*Category: timing*

- **What it does:** Boundary timers attached to a User Task (Email/General) or a Custom Function that fire an alternate outgoing flow when a configured duration elapses. Two modes: Interrupting (cancels the task when the timer fires and follows the timer's flow) and Non-Interrupting (task keeps running; timer flow also activates).
- **When to use:** For SLAs/escalations (e.g., if a user doesn't respond to a form/email within a duration, branch to an escalation path or reminder). Non-interrupting with a Time Cycle = periodic reminders while the task stays open.
- **API / JSON representation:** Conceptually BPMN boundary timer events (interrupting vs non-interrupting) with timer duration / timer cycle definitions. Not exposed via public API.
- **Config options:** Configured on a second tab of the User Task / Custom Function shape. Up to FOUR timer events per shape; each timer has exactly ONE outgoing flow. Map a value to the required 'setting' parameter — select a Duration variable or enter a custom duration. Non-Interrupting timers support a Time Cycle: every time the duration is met the flow re-activates; can repeat indefinitely or be limited to a cycle number.
- **Gotchas:** Interrupting timer CANCELS the underlying task — use non-interrupting if the task must continue. Only tasks/functions support boundary timers (not gateways). Duration must be supplied via the 'setting' parameter (Duration type).
- **Sources:** https://www.domo.com/docs/s/article/000005797

### termination

#### End shape (terminate)
*Category: termination*

- **What it does:** Terminates a workflow flow/branch. Signifies completion of the workflow.
- **When to use:** To mark the end of a path; use multiple End shapes when branches (conditional/parallel) lead to different terminal points.
- **API / JSON representation:** Conceptually a BPMN end event. When all active flows reach End, the instance status becomes COMPLETED (see instance status values). Not exposed via public API.
- **Config options:** Add via 'Flow Controls > End'. The End step has NO outgoing flows but can receive MULTIPLE incoming flows. A workflow can have multiple End shapes when the design branches.
- **Gotchas:** End has no outgoing connector by rule. In a parallel design, reaching one End does not necessarily end the whole instance if other parallel branches are still active.
- **Sources:** https://www.domo.com/docs/s/article/000005331, https://www.domo.com/docs/s/article/000005797

### entry

#### Start shape & Start Parameters
*Category: entry*

- **What it does:** The single entry point of a workflow. Defines the input parameters (with data types) that a trigger or API caller must supply to start an instance.
- **When to use:** Every workflow has exactly one Start shape; define start parameters here for any values the workflow needs at kickoff.
- **API / JSON representation:** The start 'messageName' is literally 'Start <WorkflowName>' (e.g. "Start MyWorkflow"). The public start call POST /api/workflow/v1/instances/message takes { messageName, version, modelId, data:{param1:..,param2:..} } where 'data' keys are the start parameter names. Internal app context uses POST /domo/workflow/v1/models/{alias}/start with a params body.
- **Config options:** Defaults to label 'Start [Workflow Name]'. Add parameters, each with a data type; parameters can have optional default values. The Start step has exactly ONE outgoing flow. Newer 'Initialize Variables' feature lets you assign an initial value to a variable at build time instead of forcing a start parameter or a Code Engine function to set it.
- **Gotchas:** Only one outgoing flow allowed from Start. Start parameter names must match the JSON 'data' keys exactly. 'version' and 'modelId' must match a DEPLOYED version.
- **Sources:** https://www.domo.com/docs/s/article/000005331, https://www.domo.com/docs/api-reference/workflows-api-product/start-a-workflow, https://www.domo.com/product/new-features/workflows-initialize-variables

#### Triggers (workflow entry / start events)
*Category: entry*

- **What it does:** The events that start a workflow instance. Managed on the workflow's Triggers tab (Add Trigger > <type>). These are the control-flow entry points.
- **When to use:** Choose based on how the process should kick off: user-initiated, scheduled, data-driven, or programmatic.
- **API / JSON representation:** API/programmatic start: POST /api/workflow/v1/instances/message { messageName:'Start <name>', version, modelId, data }. Internal/app: POST /domo/workflow/v1/models/{alias}/start. GET /domo/workflow/v1/models lists workflow models (returns name/alias). Each configured trigger has a trigger ID.
- **Config options:** Trigger types: (1) Manual (via Start shape, no extra setup); (2) Timer — scheduled: Every Minute, Every Hour, Every Day, Every Weekday, Every Week, Every Month; (3) Alerts — from a DataSet's Details > Alerts tab, set the Action to the workflow version; (4) API — generates JS & Python snippets containing a trigger ID; (5) App Studio — add the Workflow widget in an App Studio app; (6) Pro-Code App — configure via Asset Library/Editor; (7) Workflow / Sub-flow — another (deployed) workflow starts this one via a 'Start Workflow' action; (8) Access Request — fires when someone requests access to a Card, Page, or App. Also documented: form submission (dynamic Forms) creates a new instance.
- **Gotchas:** Triggers bind to a specific workflow VERSION — deploying a new version may require re-pointing triggers. The public start API needs a deployed model's exact modelId + version. Timer 'Every Minute' is the finest documented granularity.
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://www.domo.com/docs/api-reference/workflows-api-product/start-a-workflow, https://community-forums.domo.com/main/discussion/64876

### modularity

#### Sub Flow (sub-workflow invocation)
*Category: modularity*

- **What it does:** Calls one deployed workflow from within another, optionally capturing the child's output parameters into the parent's variables — enabling modular, reusable components.
- **When to use:** To reuse proven logic across workflows, isolate/test components independently, or decompose a large workflow. (Note: Sub Flow is the closest thing Domo offers to true iteration reuse; there is no dedicated built-in 'for-each loop' shape — looping is done with Conditional Logic back-edges or by iterating in a Code Engine function.)
- **API / JSON representation:** Conceptually a BPMN call activity. Under the hood the parent effectively triggers the child model (same start mechanism, messageName 'Start <child>'). Not exposed via public API.
- **Config options:** PREP: in the child workflow, open the Variable List, hover a variable, three-dot menu > 'Output' to mark it as an output (multiple outputs of any type allowed; removable via trash icon). USE: in parent, add/edit a step > Action Menu > 'Sub Flow' > 'Add Sub Flow' > pick a deployed, accessible workflow from dropdown/search > confirm. Choose execution mode: 'Run and Wait' (default — parent pauses until child completes; needed to capture output) or 'Run and Continue' (parent proceeds immediately; NO output captured). Map parent inputs -> child parameters (type-compatible) and child outputs -> parent variables; new variables can be auto-created.
- **Gotchas:** The child MUST be deployed and you must have access to it (only deployed, accessible workflows appear in the picker). You MUST define output parameters on the child BEFORE it can be used as a subflow. 'Run and Continue' discards outputs — use 'Run and Wait' if you need results. Requires Editor role or a custom role with 'Create Workflows' grant; if the feature is missing even with the grant, Domo account team must enable it (may be gated).
- **Sources:** https://www.domo.com/docs/s/article/000005930, https://www.domo.com/product/new-features/workflows-3

### variables

#### Variables & Data Types
*Category: variables*

- **What it does:** Typed, color-coded variables that carry values through the workflow. ~16 data types: Text, Number, Decimal, Boolean, Date, Time, Date-Time, Duration, Person, Dataset, Group, Account, File(s), Fileset, List (with an element subtype), and Object.
- **When to use:** For any value passed between steps, conditions, or in/out of tasks/functions. Duration for Wait/Timer settings; Account for secure credential references; List for collections; Object for structured/JSON payloads; Person/Group/Dataset/File/Fileset for Domo entity references.
- **API / JSON representation:** At start, variable values are passed as the 'data' object keys in the start message; at runtime variables are the process instance variables. Object child variables can be referenced individually.
- **Config options:** Managed in the Workflow variables list. Object subtypes: (1) DEFINED OBJECT — add child variables via 'Add Child' (name + data type); each child holds a single value of any type EXCEPT object (no nesting); expandable in the list. (2) OPEN OBJECT — no predefined structure; stores a JSON payload with unlimited nesting (distinguished by a different cube icon). List type requires choosing an element subtype. Account type requires a Data Provider field (e.g., Google Sheets) that restricts which accounts can be mapped. 'Initialize Variables' lets you set an initial/default value at build time. Scope: variables are workflow-instance scoped (a function output overwrites the mapped variable's prior value at runtime).
- **Gotchas:** Defined objects DO NOT support nesting (children can't be objects) — use an Open Object for nested JSON. String Builder does NOT process whole objects, but DOES process an object's child variables of the appropriate type. Account variables pass only an ID at runtime (the account service resolves it) — credentials are never stored in the workflow.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/product/new-features/workflows-initialize-variables, https://www.domo.com/product/new-features/workflows-2

### expressions

#### FEEL Expression Language (Advanced conditions)
*Category: expressions*

- **What it does:** The advanced expression syntax used to author complex conditions on conditional-gateway flows. FEEL = Friendly Enough Expression Language (the Camunda/DMN expression language).
- **When to use:** When Basic rule config isn't enough: referencing Open/Defined Object variables at the parent level, or operations unavailable in Basic. Also for complex boolean logic beyond simple AND/OR rule groups.
- **API / JSON representation:** FEEL expressions on sequence-flow conditions (BPMN/Camunda pattern). Supports FEEL contexts {} (note: {} is a context, not grouping — use () to group).
- **Config options:** Choose 'Advanced' configuration type on a conditional flow, then type a FEEL expression; you can insert workflow variables into the expression. Domo links out to external FEEL documentation (Camunda).
- **Gotchas:** {} denotes a FEEL context, a common mistake when you meant parentheses. Advanced/FEEL is the ONLY way to evaluate object variables at parent level. FEEL is distinct from Domo 'Beast Mode'/SQL — don't mix syntaxes.
- **Sources:** https://www.domo.com/docs/s/article/000005797

#### Basic condition rule editor (operators)
*Category: expressions*

- **What it does:** A no-code rule builder for conditional-gateway flows that compares a chosen variable to a value.
- **When to use:** For straightforward comparisons without writing FEEL.
- **API / JSON representation:** Compiles to a FEEL condition on the sequence flow. Not exposed via public API.
- **Config options:** In the condition modal, use the 'Datalist variable' dropdown to choose the variable to evaluate (choosing one expands the expression editor). Select a 'Comparison value type': a custom value, a null value, or another variable to evaluate against. Populate the operator/value and click 'Add Rule'. Rules in the same group are combined with AND; add a new group to combine with OR. Rules can be edited/deleted.
- **Gotchas:** The Reference article documents the mechanism but does NOT enumerate the full operator token list (equals/not-equals/greater/less/contains/in). Cannot reference whole objects here — escalate to Advanced/FEEL. Comparing against null is a first-class 'Comparison value type'.
- **Sources:** https://www.domo.com/docs/s/article/000005797

#### String Builder (expression/interpolation)
*Category: expressions*

- **What it does:** Combines custom text with workflow variables to build composite string expressions, usable anywhere a custom value can be entered.
- **When to use:** Building email/form bodies, subjects, dynamic file paths, or any parameter that mixes literal text with variable values; mapping a 'Custom' value for a Code Function parameter.
- **API / JSON representation:** Runtime string interpolation of instance variables; resolves object child variables of the correct type.
- **Config options:** Wherever you 'choose a Custom value', use String Builder to insert variables + text. At runtime the current value of each inserted variable is substituted.
- **Gotchas:** Does NOT process an entire object — only its child variables of appropriate type. Available in email/form User Tasks and any Code Function mapping.
- **Sources:** https://www.domo.com/docs/s/article/000005797

### logic

#### Custom Functions / Code Engine (Domo & external functions)
*Category: logic*

- **What it does:** Automated-task steps that run reusable logic: Domo General Utilities, Domo Text Utilities, domain packages (e.g., Equipment Maintenance), plus external functions and Code Engine (JavaScript/Python) functions. Inputs and outputs are mapped to workflow variables.
- **When to use:** For arbitrary logic Domo shapes can't express directly — including implementing loops/iteration over a list, data transforms, API calls, and computing values used by downstream conditional gateways.
- **API / JSON representation:** BPMN service-task equivalent; Code Engine functions are the scripting backbone (require('codeengine')). Not create-able via the public Workflows API.
- **Config options:** Add via Action Menu (Automated Tasks) > Domo functions / External functions / Custom functions (Code Engine). Map input parameters (dropdown shows same-type variables; 'Create Variable and Map' auto-creates+maps). Selecting a variable for an OUTPUT means the function's result overwrites that variable at runtime. Functions can be tested. Custom Functions can also carry boundary Timer Events.
- **Gotchas:** Because there is no native for-each shape, iteration over a List is commonly implemented inside a Code Engine function OR via a conditional-gateway back-edge loop; assigning a Form/user dynamically across a large list (30+) is awkward and a known pain point. Function save/deploy errors are common when code has issues.
- **Sources:** https://www.domo.com/docs/s/article/000005331, https://www.domo.com/docs/s/article/000005797

#### AI Agent Task
*Category: logic*

- **What it does:** A step embedding an autonomous AI agent that analyzes inputs, makes context-aware decisions, and performs actions using tools/data — a decision/branch-adjacent construct that can replace hand-coded conditional logic for complex routing.
- **When to use:** When decision logic is too fuzzy/complex for FEEL rules (e.g., classify a free-text request and route it), or to orchestrate multi-tool actions in one step.
- **API / JSON representation:** BPMN service/agent-task equivalent; part of Domo AI service layer. Not exposed via public API.
- **Config options:** Added from the Action menu as an 'AI Agent Task'. Redesigned config lets you describe the goal in natural language (no scripting). A 'Knowledge' tab lets the agent reference DataSets, Files, and FileSets in real time. Outputs map to workflow variables (which then feed downstream gateways).
- **Gotchas:** Non-deterministic — for auditable branching prefer explicit Conditional Logic on the agent's structured output rather than letting the agent free-route. Constrain output format (JSON schema) when its result drives a gateway.
- **Sources:** https://www.domo.com/product/new-features/workflows-2, https://www.domo.com/docs/s/article/000005331

#### Query DataSet action (Text-to-SQL + inline conditions)
*Category: logic*

- **What it does:** An automated task that runs a SQL query against a Domo DataSet, with support for inserting variables and generating SQL from natural language (Text-to-SQL). Results become variables (often an Object/List) that feed conditional branches.
- **When to use:** To fetch/compute data mid-workflow that a conditional gateway or downstream step needs (e.g., look up a threshold, count rows, retrieve a record).
- **API / JSON representation:** Backed by Domo query API (POST /api/query/v1/execute/{datasetId}). Output typically an Object/List variable referenced by later FEEL/conditions.
- **Config options:** Action Menu > Automated Tasks > Query DataSet. Choose the DataSet, write SQL (or use Text-to-SQL), insert variables into the query, map the result to an output variable.
- **Gotchas:** Returned rows arrive as JSON-like objects — to branch on a field you often need an Open Object or List variable and FEEL to extract it (referencing object values from a task output is a known question area).
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

### error-handling

#### Error handling, Recovery mode & Retry
*Category: error-handling*

- **What it does:** Post-failure/in-progress management: when a shape errors (or waits on a User Task/Wait), the execution enters a state where an authorized user can inspect, edit inputs, and Retry from the failure point, or Cancel the instance. Domo has no in-canvas try/catch or automatic retry-policy shape — error handling is operational (Recovery mode) plus design-time (default conditions, conditional branches on error variables).
- **When to use:** To recover a failed execution without re-running from scratch, to fix bad input data mid-flight, or to stop a stuck In-Progress instance.
- **API / JSON representation:** POST /api/workflow/v1/instances/{instanceId}/cancel cancels an in-progress instance (public API). Retry/Recovery-mode edits are UI-only (no documented public endpoint). Instance 'status': null, IN_PROGRESS, CANCELED, COMPLETED (also FAILED per Manage-Workflows: canvas shows failed shapes in red).
- **Config options:** Requires 'Edit Execution Details' permission. In an execution, select a shape > 'Edit Execution' in the data panel to enter Recovery mode. Options: 'Exit Recovery' (back to view-only), 'Retry' (re-run from where it failed / is in progress), 'Cancel Instance' (stop, status -> Canceled). Edit input data via the pencil icon next to an input, confirm with 'Keep' before Retry. Bulk cancel via Executions tab ('Cancel executions in bulk'). Canceled User Tasks auto-void in Task Center.
- **Gotchas:** No native try/catch/error-boundary shape and no auto-retry policy — model error paths explicitly (e.g., a Code Function returns an error flag -> Conditional Logic branch). A conditional shape with no matching condition and no Default is a common failure cause. Retried steps with external side effects are not automatically idempotent — design for it. Best practice: cancel doomed In-Progress executions so logs are accurate.
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://www.domo.com/docs/openapi/product/workflows-api.yaml, https://www.domo.com/docs/api-reference/workflows-api-product/start-a-workflow

### structure

#### Flow connector rules (shape connection constraints)
*Category: structure*

- **What it does:** Rules governing how many incoming/outgoing 'flows' (connector lines between shape ports) each shape type may have — these constraints define the control-flow graph's legality.
- **When to use:** When laying out the graph programmatically or validating a design before deploy.
- **API / JSON representation:** BPMN sequence-flow cardinality rules. Not exposed via public API.
- **Config options:** Gateways (Conditional or Parallel): MULTIPLE outgoing flows (use 'Add Gateway' for a 3rd+), single or multiple incoming. Automated/AI/Manual (User) tasks: multiple incoming, exactly ONE outgoing. Start step: exactly ONE outgoing, no incoming. End step: NO outgoing, multiple incoming allowed. Connections are drawn between circular ports on shape tiles.
- **Gotchas:** A non-gateway task can only have one outgoing flow — to branch you MUST insert a Conditional or Parallel gateway. Validation categorizes issues as Errors (red, must fix), Warnings (yellow, recommended), Informational (blue, optional); a workflow must pass validation and be deployed before it runs.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

#### Versioning & deployment (governs control-flow changes)
*Category: structure*

- **What it does:** A deployed workflow is immutable; editing requires creating a NEW version (like Save As). Versions use major.minor.patch (e.g., 1.1.2). Triggers, sub-flow references, and API start calls bind to a specific version.
- **When to use:** Whenever changing control flow (adding gateways, loops, timers) on an already-deployed workflow.
- **API / JSON representation:** Start payload requires exact 'version' + 'modelId'; response echoes 'modelVersion'. Sub-flows and triggers reference deployed versions.
- **Config options:** Versions list from Workflows home; edit a pre-deployed version via More > Edit Workflow (locked to one editor at a time — others get a 'Version Locked' modal). Deploy before it can run or be used as a subflow/trigger target.
- **Gotchas:** You cannot edit a deployed version in place. Changing control flow means a new version + re-pointing triggers and parent sub-flow references, and updating any API 'version' string. Pre-deployed versions are single-editor locked.
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://www.domo.com/docs/api-reference/workflows-api-product/start-a-workflow

**Open questions / not fully verified:**

- Domo does not publicly expose the underlying workflow model JSON/BPMN-XML (the OpenAPI spec only documents start/cancel/permissions). The internal representation is strongly inferable as BPMN 2.0 / Camunda-Zeebe (FEEL expression language, interrupting/non-interrupting boundary timers, time cycles, exclusive/parallel gateways, call activities), but exact 'type' strings and a designElements schema could not be confirmed from official docs. An AI authoring workflows programmatically must build them via the UI/canvas or reverse-engineer the private model API; there is no documented create-from-JSON endpoint.
- The public Workflows API (workflows-api-product) documents only POST /instances/message (start), POST /instances/{instanceId}/cancel, and POST /models/{modelId}/permissions. Listing models, reading versions, and reading execution/instance details appear only via undocumented internal endpoints (/domo/workflow/v1/models, /api/workflow/v1/models/{alias}/start). Exact schemas for those are unconfirmed.
- The complete operator list for Basic conditional configuration (equals, not equals, greater/less than, contains, in, etc.) is not enumerated in the Reference article; the docs describe the mechanism (Datalist variable dropdown -> expression editor -> Comparison value type -> Add Rule) but not each operator token.
- Whether the 'Wait' Flow Control supports absolute date/datetime targets vs relative durations is not spelled out in the Reference article (Create-a-Workflow only says Wait 'delays workflow execution'); duration is expressed via Duration data type/variables.

## Triggers & entry points

### start-config

#### Start shape (start event / manual trigger)
*Category: start-config*

- **What it does:** Every workflow has one Start shape that marks the beginning of the process and has exactly one outgoing flow. Configuring the Start shape IS how you set up the built-in manual trigger. Default title is 'Start {Workflow Name}'; this title doubles as the workflow's message start event name (the 'messageName' used by the API). You can rename it by double-clicking the shape or editing the title field in the right-hand configuration panel, and add a workflow description there.
- **When to use:** Always required. Use manual start for human-initiated runs, testing, or when the workflow is launched from the version list / canvas rather than by an automated trigger.
- **API / JSON representation:** Start shape corresponds to a message start event. Its title becomes 'messageName' in the Start-a-Workflow API ('usually Start {workflow_name}'). Docs call it the 'Start step'. The exact internal JSON field names for the start event id / manual trigger id are not exposed in public docs; the observable identifier is 'messageName' (plus modelId + version).
- **Config options:** Title (= message start event name), description, and the list of start parameters. Manual trigger needs no separate setup and works even before deployment (all other trigger types require deployment first).
- **Gotchas:** Only one Start shape per workflow. Renaming the Start shape changes the messageName the API must send. Manual triggers are the ONLY trigger configurable before deployment.
- **Sources:** https://www.domo.com/docs/s/article/000005331, https://www.domo.com/docs/s/article/000005179, https://www.domo.com/docs/s/article/000005797

#### Start parameters / Start Form (input parameters)
*Category: start-config*

- **What it does:** Parameters defined on the Start shape are the inputs passed into a workflow at launch. When a workflow is started manually, these render as a Start Form the user fills in; when started by API/trigger they are supplied as a data object. Each parameter auto-maps to a workflow variable of the same name and data type.
- **When to use:** Whenever the workflow needs input values (from a human form, an alert's row data, an app, or an API caller).
- **API / JSON representation:** In the Start-a-Workflow API these are supplied under the 'data' object keyed by parameter name, e.g. "data": { "parameter1": 13, "parameter2": 7 }. In the pro-code app manifest, each parameter is an object with fields: name, aliasedName (the alias the app passes in), type (one of the data-type strings above), list (boolean), optional value (default), optional children (nested object props).
- **Config options:** Per parameter: Name (no spaces or special characters), Data type, Required toggle (required params show a red asterisk), and optional default value via 'Add Default Value' (params with a default show a blue dot). Defaults are editable only until the version is deployed. Data types available: boolean, date, dateTime, decimal, duration, number, object, person, dataset, group, text, time (also 'list' variants = accepts multiple values). Related feature 'Initialize Variables' lets you assign an initial value to a variable during version building, avoiding an unnecessary start parameter.
- **Gotchas:** Parameter names cannot contain spaces/special characters. Required parameters must be populated or mapped before a trigger can be saved. Default values freeze at deploy time.
- **Sources:** https://www.domo.com/docs/s/article/000005331, https://www.domo.com/docs/portal/Apps/App-Framework/Guides/hitting-a-workflow, https://www.domo.com/product/new-features/workflows-initialize-variables

### trigger-scheduled

#### Timer trigger (scheduled)
*Category: trigger-scheduled*

- **What it does:** Runs a deployed workflow version on a recurring schedule. Configured from the workflow's Triggers tab after deployment; you pick the version, then an interval and start time. Setting a timer makes the version 'Active'.
- **When to use:** For unattended recurring automation (periodic data processing, scheduled notifications, polling-style jobs).
- **API / JSON representation:** Represented as a trigger entry on the workflow version (surfaced in the Triggers tab). Deletable via the trash-can icon in its config modal. Public JSON schema for the timer trigger object is not documented.
- **Config options:** Interval options observed: Every Minute (every 1, 5, or 15 minutes, optional 'Start Between' window), Every Hour (optional 'Start Between' hours window), Every Day (single daily run at chosen hour), Every Weekday (Mon-Fri at chosen hour), Every Week (chosen day + hour), Every Month (1st, 15th, or last day at chosen hour). Choose the workflow version to run.
- **Gotchas:** Requires the workflow to be deployed first (cannot set a timer on an undeployed version). 'Active' = currently configured to run on a schedule/trigger; you can Deactivate to stop runs without deleting. Triggers cannot be copied from one version to another.
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://www.domo.com/docs/s/article/000005331

### trigger-programmatic

#### API trigger (HTTP call from Triggers tab)
*Category: trigger-programmatic*

- **What it does:** Creates an externally-callable HTTP trigger. In the Triggers tab you add an API trigger and select the workflow version; Domo auto-generates ready-to-paste JavaScript AND Python snippets containing a unique trigger ID. This is Domo's equivalent of a webhook-style inbound start.
- **When to use:** To start a workflow from external systems, scripts, scheduled jobs, or any HTTP client. This is the path to use when the skill author wants programmatic launch outside App Studio/pro-code.
- **API / JSON representation:** Underlying call is POST https://{instance}.domo.com/api/workflow/v1/instances/message with body { messageName, version, modelId, data:{...params} } (see 'Start a Workflow REST API' feature). The API trigger's unique triggerId is what appears in execution records.
- **Config options:** Select workflow version; copy generated JS/Python. The generated code embeds a unique trigger ID that exclusively tracks which trigger initiated each execution (useful for attributing runs in the DomoStats Workflows report).
- **Gotchas:** Requires deployment first. Deletable via trash-can icon in the trigger's config modal. There is no separate 'Webhook' trigger type in Domo Workflows — the API trigger fills that role. (Alert 'Webhook' actions are outbound to third parties, a different feature.)
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://www.domo.com/docs/api-reference/workflows-api-product/start-a-workflow, https://www.domo.com/product/new-features/domo-workflows

#### Pro-Code app trigger (App Framework / ryuu proxy)
*Category: trigger-programmatic*

- **What it does:** Lets a custom (pro-code) Domo app start a deployed workflow through the client-side proxy, using an alias declared in the app manifest that is wired to a real workflow model+version at publish time.
- **When to use:** When embedding workflow launch into a custom-coded Domo app / card UI (buttons, forms in your own HTML/JS app).
- **API / JSON representation:** Client call: domo.post(`/domo/workflow/v1/models/${alias}/start`, body) where body keys match the parameters' aliasedName values. The alias is resolved server-side to the wired modelId+version (a snapshot on the card instance).
- **Config options:** In manifest.json add a 'workflowsMapping' array. Each entry: alias (string, referenced in code), modelId (null until wired), version (null until wired), parameters[] each with name, aliasedName (alias of the param you pass in), type (boolean|date|dateTime|decimal|duration|number|object|person|dataset|group|text|time), list (boolean), optional value (default), optional children (nested props). Set proxyId in manifest for local testing. After publishing, wire each alias to an actual workflow via the card editing/wiring screen — the wiring options are exactly the aliases in workflowsMapping.
- **Gotchas:** Requires deployment first. modelId/version are null in the manifest and only bound at wiring time (like CE aliases, the binding is a snapshot on the card instance — re-wire if you point to a new version). A 404 on the start call typically means the alias isn't wired or the version isn't deployed. Do not hardcode modelId in the manifest; wire it.
- **Sources:** https://www.domo.com/docs/portal/Apps/App-Framework/Guides/hitting-a-workflow, https://community-forums.domo.com/main/discussion/68592/starting-a-workflow-from-a-domo-app

### api

#### Start a Workflow REST API (message endpoint)
*Category: api*

- **What it does:** The public REST endpoint that starts a deployed workflow instance by sending a message to its start event.
- **When to use:** Programmatic launch from any authenticated HTTP client / server-side integration.
- **API / JSON representation:** Response = a WorkflowInstance object: id, modelId, modelName, modelVersion, createdBy/updatedBy, createdOn/updatedOn, status (null | IN_PROGRESS | CANCELED | COMPLETED; null = not yet reporting). Status codes: 200 success, 400 invalid params, 401 auth failure, 404 workflow not found. Operation tags in the reference: 'Workflow Instances' and 'Workflow Models' (implying additional model/version and instance-status endpoints under /api/workflow/v1/ though not detailed in the excerpt).
- **Config options:** Method POST; URL https://{instance}.domo.com/api/workflow/v1/instances/message. Body fields: messageName (string, the start-event message, usually 'Start {workflow_name}' = Start shape title), version (string, e.g. '0.0.1'), modelId (string GUID = the workflow's ID), data (object of start parameters keyed by name). Auth header X-DOMO-Developer-Token (API key). OAuth scope for the Workflows API family is 'workflow'.
- **Gotchas:** messageName must exactly match the Start shape title, and modelId+version must reference a DEPLOYED version, or you get 400/404. modelId is a GUID, not the numeric workflow id. This same call underlies the auto-generated API-trigger snippets.
- **Sources:** https://www.domo.com/docs/api-reference/workflows-api-product/start-a-workflow, https://prismatic.io/docs/components/domo/

### trigger-event

#### App Studio trigger (Workflow widget/button)
*Category: trigger-event*

- **What it does:** Adds a workflow launch control inside an App Studio app so end-users can start a deployed workflow version from the app UI.
- **When to use:** For no-code embedding of workflow start into an App Studio dashboard/app for business users.
- **API / JSON representation:** Creates a trigger entry visible in the workflow's Triggers tab. Because it's configured from the App Studio feature, it must be deleted from within App Studio (not from the Triggers tab).
- **Config options:** Add a Workflow widget in the App Studio app, then select the desired workflow version from the versions shown in the widget. Start parameters can be supplied/mapped from the app context.
- **Gotchas:** Requires deployment first. Requires Manage Workflows grant + Admin or Execute permission to configure. Delete from the originating feature (App Studio), not the Triggers modal.
- **Sources:** https://www.domo.com/docs/s/article/000005179

#### Alert trigger (DataSet alert action)
*Category: trigger-event*

- **What it does:** Runs a deployed workflow when a Domo Alert fires. This is the documented path for 'when a dataset changes/threshold is met, start a workflow' — dataset-condition alerts execute the workflow as their Action, and alert parameters (row values from the dataset/card) can be passed into the workflow's start parameters.
- **When to use:** Event-driven automation off data conditions: threshold breaches, new rows meeting a case, KPI alerts. This is how you approximate a 'dataset-updated' or data-condition trigger for workflows.
- **API / JSON representation:** Surfaces as a trigger on the workflow (Triggers tab) but is configured/managed from the Alert. Delete from the Alert feature. Note: an Alert can alternatively attach an outbound 'Webhook' action (POST/PUT/PATCH/GET/DELETE to a third-party URL) — that is separate from starting a Domo workflow.
- **Config options:** On the DataSet's Alerts tab, create/edit an Alert and set its Action to the workflow version to execute. Alert parameters linked to the dataset/card map into the workflow's start parameters (types must align). Alert conditions are configured in the standard Alert wizard.
- **Gotchas:** Requires the workflow to be deployed first. There is NO first-class 'DataSet updated' workflow trigger — dataset/data-driven starts route through Alerts (community confirms workflows are triggered only via schedule, alert, or API). Contrast with DataFlow triggering ('When DataSets update' in a DataFlow's Settings tab), which is a DataFlow feature, not a Workflow trigger.
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://knowledge.domo.com/Optimize/Notifications_and_Alerts/Creating_an_Alert_for_a_DataSet, https://community-forums.domo.com/main/discussion/68120/workflow-triggers-using-activity-log-events, https://www.domo.com/docs/s/article/000005216

#### Workflow-to-workflow trigger (Start Workflow action step)
*Category: trigger-event*

- **What it does:** One workflow starts another. Achieved by adding a 'Start Workflow' action step inside the initiating workflow that references the target workflow and maps parameters between them.
- **When to use:** Orchestration / decomposition — chaining or fanning out to sub-workflows.
- **API / JSON representation:** Modeled as an action/function step in the initiating workflow (not a standalone trigger config); it produces a trigger entry on the callee. Managed/deleted from the initiating workflow.
- **Config options:** In the initiating workflow's edit mode: search for and add the 'Start Workflow' action step, select the target workflow from the function list, map required parameters, then deploy the initiating workflow. The resulting trigger appears in the target's Triggers tab.
- **Gotchas:** The initiating (triggering) workflow must be deployed. Triggers cannot be copied between workflow versions. Target must be deployed to be selectable.
- **Sources:** https://www.domo.com/docs/s/article/000005179

#### Access Request trigger
*Category: trigger-event*

- **What it does:** Starts a deployed workflow each time a user requests access to a selected Card, Page, or App — e.g. to run a custom approval flow.
- **When to use:** Automating access-request/approval processes for governance.
- **API / JSON representation:** Trigger entry on the workflow version (Triggers tab). Executes on every access request to the chosen entity type.
- **Config options:** In the Triggers menu choose 'Access Request', pick the entity type (App, Card, or Page), optionally map Access Request Details (Requestor ID and entity ID) to workflow start parameters when data types align, name the trigger, and populate/map all required start parameters before saving. The workflow runs under the account that created the trigger.
- **Gotchas:** Requires deployment first. Runs as the trigger creator's user (permission implications). Requires Manage Workflows grant + Admin/Execute permission.
- **Sources:** https://www.domo.com/docs/s/article/000005179

### management

#### Triggers tab & trigger management
*Category: management*

- **What it does:** Central place (per workflow, reached from Workflows home > select a workflow) listing every trigger configured for a workflow version, with Add Trigger and per-trigger config. A product-level 'Workflow Triggers' view centralizes all trigger integrations (Alerts, App Studio, Pro Code Apps, Timers, APIs) and identifies the exact trigger behind any given execution.
- **When to use:** To add/inspect/remove automated triggers and to audit how a workflow gets started.
- **API / JSON representation:** Deletion rules: Timer and API triggers delete via the trash-can icon in their config modal; Alert, App Studio, Pro-Code, and Workflow triggers must be deleted from the feature where they were configured. Each execution can be attributed to its originating triggerId (also captured by the DomoStats Workflows connector/report).
- **Config options:** Add Trigger button; configure timer/API/Access Request here; alert/App Studio/pro-code/workflow triggers are configured from their originating feature but still listed here.
- **Gotchas:** Only manual triggers can be configured pre-deployment; all others require a deployed version. Configuring any non-manual trigger requires Manage Workflows grant + Admin or Execute permission on the workflow. Triggers cannot be copied between versions. Version states: Deployed (validated, runnable), Active (currently set to run on schedule/trigger); Deactivate stops runs without deleting.
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://www.domo.com/product/new-features/domo-workflows

#### Deployment & version prerequisites for triggers
*Category: management*

- **What it does:** Governs when triggers can exist. A workflow must be Validated then Deployed before any automated trigger works; versions use major.minor.patch and the trigger/API references a specific version.
- **When to use:** Author must deploy a version before wiring timers, API, App Studio, pro-code, alert, workflow, or access-request triggers; and must pass the matching version string in API/message calls.
- **API / JSON representation:** modelId (GUID) + version (string) uniquely identify the runnable target in the Start-a-Workflow API and in pro-code wiring (modelId/version on the workflowsMapping entry / card instance).
- **Config options:** Validate (errors block, warnings optional) -> Deploy -> version becomes runnable; Active when a trigger/timer is attached. Version format <<major.minor.patch>>.
- **Gotchas:** Manual start still requires the version to be Deployed and Active to run from the version list/canvas. Sending an API message to an undeployed/incorrect version -> 404/400. Only one user can edit a pre-deployed version at a time.
- **Sources:** https://www.domo.com/docs/s/article/000005331, https://www.domo.com/docs/s/article/000005179

**Open questions / not fully verified:**

- Domo's public docs do not expose the raw workflow model JSON with the exact field names the task hypothesized (triggers[], manualTriggerId, startEventId). The documented/observable equivalents are: the start event addressed by 'messageName' (= Start shape title), the workflow identified by 'modelId'+'version', and each configured trigger carrying a unique triggerId surfaced in execution records. Confirming the literal model-schema field names would require inspecting a live /api/workflow/v1/models/{id} response or the workflow-authoring SDK.
- The Start-a-Workflow API reference names two operation tags ('Workflow Instances', 'Workflow Models') implying additional endpoints (list/get instances for status polling, list models/versions) under /api/workflow/v1/, but the fetched excerpt only detailed POST /instances/message. The exact GET paths for polling instance status and enumerating deployed versions/modelIds should be confirmed from the full API reference.
- There is no first-class 'AppDB trigger' or 'DataSet-updated trigger' for Workflows in current official docs. Dataset/data-condition starts go through Alerts; AppDB-change-initiated starts are not documented (would require an Alert on a dataset synced from AppDB, or a Code Engine/API call). Worth explicitly flagging to the skill author so it doesn't emit a non-existent trigger type.
- Timer interval enumeration (every 1/5/15 min, hourly, daily, weekday, weekly, monthly on 1st/15th/last) came from a doc extraction; the precise 'Start Between' window semantics and timezone handling should be verified against the live Triggers UI.
- The pro-code proxy path domo.post('/domo/workflow/v1/models/{alias}/start', body) vs the token-auth public path /api/workflow/v1/instances/message are two distinct mechanisms; whether the pro-code alias path also accepts messageName/version overrides (vs relying solely on the wired modelId/version) is not fully documented.

## Action steps (Domo actions & Code Engine functions)

### architecture

#### ARCHITECTURE NOTE — most 'Domo actions' are Code Engine packages, not dedicated tiles
*Category: architecture*

- **What it does:** Critical framing for an authoring AI: the Domo Workflow editor has only a SMALL set of truly first-class native task tiles (Query DataSet, Email user task, General Task, Sub Flow, AI Tools, AI Agent Task, plus flow controls). Everything else the prompt asks about — writing/appending/updating a DataSet, AppDB (Data Store) document CRUD, posting to Buzz, Slack/Teams messaging, creating/managing cards & pages, running a DataFlow, managing users/groups, file/fileset actions, styled notifications — is delivered as an 'action' by selecting a FUNCTION from a Code Engine package under the 'Domo Functions' (Domo-authored), 'External Functions' (external systems), or 'Custom Functions' (your own) menu, and mapping workflow variables to that function's inputs/outputs. Under the hood each such action is a Code Engine function that calls Domo internal REST APIs via codeengine.sendRequest(method,url) (credentials of the authenticated user are auto-injected) or calls external services via codeengine.axios / codeengine.getAccount.
- **When to use:** Read this before trying to author any DataSet-write, AppDB, Buzz, Slack/Teams, card/page, dataflow-run, user/group, or file action. Do NOT assume a drag-and-drop tile exists for these; author or select a Code Engine function instead.
- **API / JSON representation:** Workflow model node references a Code Engine function by package id + version + function name with input/output variable bindings; the function body uses require('codeengine') → codeengine.sendRequest('get|post|put|delete', url), codeengine.getAccount, codeengine.axios.
- **Config options:** A function node exposes: package selection, function selection, version, a Mapping tab (map workflow variables to typed function inputs; create+auto-map output variables), and a Timer tab (up to 4 timer events).
- **Gotchas:** Domo does NOT publish a catalog of its built-in Code Engine packages/functions (open community request 'Domo provided Code Engine Package Documentation' is unresolved). Names/signatures are discoverable only in-product via the action menu search box. Plan for the authoring AI to enumerate available functions at build time rather than hardcode names.
- **Sources:** https://www.domo.com/docs/s/article/000005173, https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331, https://community-forums.domo.com/main/discussion/71201/domo-provided-code-engine-package-documentation

### native-automated-task

#### Query DataSet (a.k.a. Query Table)
*Category: native-automated-task*

- **What it does:** First-class native automated task that queries and RETRIEVES data from a Domo DataSet inside the workflow. You name the query and build a SQL query (with a Create SQL Query modal); supports natural-language Text-to-SQL, embedding workflow variables in the query, and previewing results before sending.
- **When to use:** Whenever the workflow needs to read rows/values from a DataSet to drive logic. This is the only native (non-code) way to touch a DataSet.
- **API / JSON representation:** Backed internally by the query-dataset API (/docs/openapi/product/query-dataset-api.yaml). Output bound to a workflow variable (often a List<Object> or Object).
- **Config options:** Query name; DataSet selection; SQL query (typed or Text-to-SQL generated); variable insertion into the query; output type/variable definition; preview/run.
- **Gotchas:** It READS only — there is no native tile to write/append/update a DataSet. For writeback you must use a Domo Function / Code Engine (sendRequest to the DataSet/Stream API) — see the DataSet write action entry.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

#### Sub Flow (call another workflow)
*Category: native-automated-task*

- **What it does:** Embeds/calls one workflow from within another, captures its outputs, and uses those values in later steps of the parent — enabling modular, reusable sub-flows.
- **When to use:** Break complex processes into testable, reusable pieces; avoid duplicating logic.
- **API / JSON representation:** Native node; conceptually similar to the 'Start Workflow' package but for composition within the canvas.
- **Config options:** Select target workflow; map input parameters; capture outputs into parent variables.
- **Gotchas:** Newer capability (added to the action menu). Sub-flows can be tested in isolation.
- **Sources:** https://www.domo.com/docs/s/article/000005331, https://www.domo.com/product/new-features/workflows-3

#### AI Tools — Domo AI Service Layer
*Category: native-automated-task*

- **What it does:** Native AI automated task exposing pre-built Domo AI functions: Image to Text, Text Generation, and Text to SQL.
- **When to use:** In-workflow generative/AI steps: OCR/vision (image→text), LLM text generation, or natural-language→SQL for querying.
- **API / JSON representation:** Grouped under 'AI Tools' in the action menu; backed by Domo AI service.
- **Config options:** Select the AI function (Image to Text / Text Generation / Text to SQL); map input variables (prompt, image, schema); output variable.
- **Gotchas:** Subject to Domo AI enablement/credits and instance AI governance settings.
- **Sources:** https://www.domo.com/docs/s/article/000005331

#### AI Tools — Domo Jupyter (run notebook)
*Category: native-automated-task*

- **What it does:** Executes a Jupyter Notebook / Jupyter workspace from within a workflow as an automated task.
- **When to use:** Leverage Python/ML notebooks in a pipeline (e.g., scoring, transforms) as a workflow step.
- **API / JSON representation:** Grouped under 'AI Tools' in the action menu.
- **Config options:** Select the Jupyter workspace/notebook; map inputs/outputs.
- **Gotchas:** Requires Jupyter Workspaces to be provisioned in the instance.
- **Sources:** https://www.domo.com/docs/s/article/000005331

#### AI Agent Task
*Category: native-automated-task*

- **What it does:** Embeds an AI agent that analyzes inputs, makes context-aware decisions, and executes actions using tools, data, and functions.
- **When to use:** Autonomous/agentic steps where the model chooses tools/functions to accomplish a goal within the flow.
- **API / JSON representation:** Native task type surfaced in the action menu (ties to Domo AI Agents / AI toolkits).
- **Config options:** Agent selection/configuration; available tools/functions and data; input/output mapping.
- **Gotchas:** Newer capability; depends on AI Agents feature being enabled.
- **Sources:** https://www.domo.com/docs/s/article/000005331

#### Custom Functions (your Code Engine packages)
*Category: native-automated-task*

- **What it does:** Executes a user-authored Code Engine function (JavaScript or Python) as a workflow action. Categories seen in-product include 'Domo General Utilities', 'Domo Text Utilities', and sample packs like 'Equipment Maintenance'.
- **When to use:** Any bespoke logic, internal API call, or external API call not covered by a native tile or a Domo/External function.
- **API / JSON representation:** Code Engine function: require('codeengine'); use codeengine.sendRequest (internal Domo APIs, user creds auto-injected), codeengine.getAccount (stored account creds), codeengine.axios (external HTTP). 13 input/output types: Account, Boolean, DataSet, Date, Datetime, Decimal, Duration, Group, Number, Object (Open/Defined), Person, Text, Time.
- **Config options:** Mapping tab (map inputs/outputs, supply custom input values matching the param data type, auto-create+map output variables); Timer tab (up to 4 timer events); a Start Function testing modal for pre-deploy validation. Supports multiple incoming flows but one outgoing flow.
- **Gotchas:** Requires 'Create Code Engine Packages' grant. Packages are semantically versioned; the workflow binds a specific version. node -c / ast.parse won't catch runtime scope errors — test via the modal.
- **Sources:** https://www.domo.com/docs/s/article/000005173, https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

#### External Functions
*Category: native-automated-task*

- **What it does:** Pre-built functions that integrate with EXTERNAL systems/APIs (e.g., the built-in Twilio package for SMS via sendTwilioSms).
- **When to use:** Calling third-party SaaS/APIs (SMS, external services) as a workflow step.
- **API / JSON representation:** Code Engine functions using codeengine.getAccount + codeengine.axios. Named built-in: Twilio (sendTwilioSms).
- **Config options:** Select external package/function; map inputs; typically requires an Account (Data Provider) variable for credentials.
- **Gotchas:** Account data type must be mapped to an account created by or shared with the user; it passes an account ID that the account service resolves and injects over HTTPS.
- **Sources:** https://www.domo.com/docs/s/article/000005173, https://www.domo.com/docs/s/article/000005797

### domo-function

#### DataSet create / append / update (via Domo Functions / Code Engine)
*Category: domo-function*

- **What it does:** Writes back to Domo DataSets from a workflow: create a DataSet, append/replace rows, update schema, or execute a DataFlow. Delivered through the Domo-provided 'Domo DataSets' Code Engine package and/or custom functions using codeengine.sendRequest to internal DataSet/Stream APIs.
- **When to use:** Any time a workflow must persist data to a DataSet, log an execution, or kick off/refresh a DataFlow.
- **API / JSON representation:** codeengine.sendRequest('get','api/data/v3/datasources/{id}?part=core,permission,status,pdp,rowcolcount,certification,functions') for metadata; write/append via Stream API (/docs/openapi/platform/stream.yaml, Stream-API) and dataset API (/docs/openapi/platform/dataset.yaml). Example built-in function: getDataSetMetadata(dataSetId).
- **Config options:** Select the DataSet function; map inputs (DataSet id, rows/payload, schema); output variable for status/result.
- **Gotchas:** No dedicated GUI tile; must go through a function. Large writes should use Streams for performance (matches Domo SDK guidance).
- **Sources:** https://www.domo.com/docs/s/article/000005173, https://www.domo.com/docs/llms.txt

#### Run / trigger a DataFlow (via Code Engine)
*Category: domo-function*

- **What it does:** Executes or refreshes a Magic ETL / SQL DataFlow (or DataSet refresh) as part of a workflow pipeline. Domo markets Workflows as able to 'trigger DataFlows' and 'automate the updating or export of datasets'.
- **When to use:** Orchestration pipelines: load new data → run DataFlow → attach calculations → notify stakeholders.
- **API / JSON representation:** codeengine.sendRequest POST to the internal dataflow execution endpoint; no public OpenAPI tile, done inside a Code Engine function.
- **Config options:** Function inputs: DataFlow/DataSet id; output: run/execution id or status.
- **Gotchas:** Not a labeled native tile — implemented as a Domo/custom function. Long-running DataFlows will not block-complete inside the tile; design async (poll status) if needed.
- **Sources:** https://www.domo.com/automation/workflows, https://www.domo.com/docs/portal/Automate-Actions/Workflows/overview

#### AppDB / Data Store document CRUD (via Code Engine)
*Category: domo-function*

- **What it does:** Create, read, query, update (replace or partial), and delete documents in an AppDB collection (Data Store) from a workflow. There is no dedicated AppDB tile; it is done via a Code Engine function calling the AppDB REST API.
- **When to use:** Persisting workflow state, records, or app data in a schemaless collection; reading config/settings documents; logging.
- **API / JSON representation:** codeengine.sendRequest to /api/datastores/v2/collections/{collectionId}/documents — POST (create), GET /{documentId} (read), PUT /{documentId} (replace), DELETE /{documentId}, POST /query (MongoDB-style predicates; supports groupby,count,avg,min,max,sum,unwind,orderby,limit,offset; $where/$near/$nearSphere unsupported), POST /bulk (bulk create), PUT /bulk (bulk upsert), DELETE /bulk?ids=, PUT /update (partial). Document JSON: id, content, datastoreId, collectionId, owner, createdBy, updatedBy, createdOn, updatedOn, syncRequired. Collections: /api/datastores/v1/collections.
- **Config options:** Inputs: collectionId, document content (arbitrary JSON), documentId, query predicate; output: document(s) / id.
- **Gotchas:** You can only write the 'content' object; the envelope (id/timestamps/owner) is system-managed. There is a matching AppDB variable type only indirectly (Object/Open Object holds the JSON). Public API also exists at /docs/api-reference/app-db-api-product/create-document.
- **Sources:** https://www.domo.com/docs/openapi/product/appdb.yaml, https://www.domo.com/docs/api-reference/app-db-api-product/create-document, https://www.domo.com/docs/llms.txt

#### Domo Notifications (styled email) package
*Category: domo-function*

- **What it does:** Domo-provided Code Engine package that delivers styled/formatted email from a workflow (richer than the raw Email user task).
- **When to use:** When you need formatted notification emails driven by workflow data rather than a response-button user task.
- **API / JSON representation:** Code Engine package 'Domo Notifications'; invoked as a Domo Function node.
- **Config options:** Function inputs: recipients, subject, body/template, variables.
- **Gotchas:** Distinct from the Email User Task; no response-button routing. Named explicitly in the Code Engine docs as a built-in package.
- **Sources:** https://www.domo.com/docs/s/article/000005173

#### Start Workflow (workflow-to-workflow trigger) package
*Category: domo-function*

- **What it does:** Lets one workflow trigger another workflow. Search 'Start Workflow' in the action menu, select the target workflow from the function list, and map the necessary parameters.
- **When to use:** Chaining/orchestrating independent workflows (vs. embedding via Sub Flow).
- **API / JSON representation:** Code Engine package 'Start Workflow'; internally posts to the workflow start endpoint.
- **Config options:** Target workflow selection; parameter mapping; deploy.
- **Gotchas:** Distinct from Sub Flow (which returns outputs into the parent). Requires the target workflow to be deployed.
- **Sources:** https://www.domo.com/docs/s/article/000005179

#### Buzz message post (via Code Engine)
*Category: domo-function*

- **What it does:** Posts a message to a Domo Buzz conversation/channel from a workflow. No dedicated Buzz tile exists; implemented as a Code Engine function calling the internal Buzz API.
- **When to use:** Notify a team channel in Buzz when a workflow event occurs (e.g., form submitted, anomaly detected).
- **API / JSON representation:** codeengine.sendRequest POST to internal Buzz messaging endpoint (no public OpenAPI tile).
- **Config options:** Function inputs: conversation/channel target, message text, mentions.
- **Gotchas:** Not a native action node; frequently requested but must be coded. Buzz is Domo's Slack-like internal chat.
- **Sources:** https://www.domo.com/docs/s/article/360042925574, https://community-forums.domo.com/main/discussion/66762/getting-buzz-message-when-a-form-submitted

#### Cards & Dashboards/Pages management (via Code Engine)
*Category: domo-function*

- **What it does:** Create/manage cards, dashboards, and pages from a workflow. The Code Engine docs explicitly list APIs 'for user/group management, cards, and dashboards' as callable. No dedicated card/page tiles.
- **When to use:** Programmatically provision or update cards/pages, fetch a KPI card image, or manage page layout as part of automation.
- **API / JSON representation:** codeengine.sendRequest to card/page internal APIs (public specs: /docs/openapi/product/cards.yaml, /docs/openapi/product/pages-api.yaml, get-kpi-card-image-api.yaml, Card-API, Page-API).
- **Config options:** Function inputs: card/page ids, definitions; outputs: created ids.
- **Gotchas:** Not a native tile; requires coding against internal APIs. Card/page schemas are complex.
- **Sources:** https://www.domo.com/docs/s/article/000005173, https://www.domo.com/docs/llms.txt

#### Users & Groups management (via Code Engine)
*Category: domo-function*

- **What it does:** Create/read/update users and manage groups (add/remove members) from a workflow. Code Engine docs list user/group management APIs as callable via sendRequest.
- **When to use:** Onboarding/offboarding automation, dynamic group membership, resolving a Person's email (People API) for notifications.
- **API / JSON representation:** codeengine.sendRequest to user/group internal APIs (public specs: /docs/openapi/product/user-api.yaml, groups-api.yaml, User-API, Group-API). Person and Group are native workflow variable data types.
- **Config options:** Function inputs: user/group ids, attributes, membership arrays; Person/Group variable types available for mapping.
- **Gotchas:** Not a native tile. Note: Code Engine get_execution_information() may return an empty userEmail — resolve recipient email via People API fallback.
- **Sources:** https://www.domo.com/docs/s/article/000005173, https://www.domo.com/docs/llms.txt

#### Files & Filesets actions
*Category: domo-function*

- **What it does:** Work with files and filesets in a workflow. 'Files' and 'Fileset' are native workflow VARIABLE data types (so files can be passed between steps), while the actual file/fileset operations (upload/download/list) are performed via Code Engine functions calling the Files/Fileset APIs.
- **When to use:** Attaching, generating, moving, or reading files/filesets within an automation (e.g., process an uploaded file, produce an export).
- **API / JSON representation:** codeengine.sendRequest to file APIs (public specs: /docs/openapi/product/files.yaml, filesets.yaml, framework files.yaml, file-set.yaml). Variable types: Files, Fileset.
- **Config options:** Map Files/Fileset variables into functions; function inputs: file ids, fileset ids, content.
- **Gotchas:** The variable types are first-class, but the read/write operations are function-based, not dedicated tiles.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/llms.txt

### native-user-task

#### Email — User Task (native send email)
*Category: native-user-task*

- **What it does:** Native User Task that automatically sends an email to chosen recipients; the email body can embed response buttons so recipients reply directly from the email, and the chosen response routes the workflow. Supports multiple incoming flows, single outgoing flow.
- **When to use:** Human-in-the-loop notifications and approvals where the recipient must acknowledge or choose an option that steers the flow (e.g. Response Required email).
- **API / JSON representation:** Native workflow user-task node type (not a Code Engine function).
- **Config options:** Recipient specification (Person variable/user); email message body with variable insertion via String Builder (combine custom text + variables); response options each defined by data type, button label, and response value.
- **Gotchas:** Emails can only be sent to DOMO USERS (recipients must exist as Domo users). Sender is Domo's notification address (notifications@domo.com); custom From-domain and CC are commonly requested but limited. For richer/styled email to broader audiences use the 'Domo Notifications' package instead.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331, https://community-forums.domo.com/main/discussion/69489/sendemail-in-domo-workflows

#### General Task — User Task (forms/queues)
*Category: native-user-task*

- **What it does:** Native User Task assigning human work that is completed by submitting a form. Routes work to a queue and/or specific users; the form's fields map to workflow variables.
- **When to use:** Task Center / human approval steps where a person fills out a form to advance the process.
- **API / JSON representation:** Native workflow user-task node; forms are a separate Workflows feature (KB article 000005171). Multiple incoming, single outgoing flow.
- **Config options:** Queue selection; user assignment; form creation or selection; parameter mapping for form variables (required params marked with a red asterisk must be mapped).
- **Gotchas:** Requires a Form to be built/selected; unmapped required parameters block a valid configuration.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

### external-integration

#### Slack / Microsoft Teams messaging (via Code Engine or Alert webhook)
*Category: external-integration*

- **What it does:** Sends messages to Slack or Microsoft Teams. Domo Workflows have NO first-class Slack/Teams action node.
- **When to use:** Cross-tool notifications to Slack/Teams channels.
- **API / JSON representation:** codeengine.axios(POST, webhookUrl, {text/blocks}); or Alert Webhook action with JSON body + Domo merge codes.
- **Config options:** Two paths: (1) Code Engine function using codeengine.axios to POST to a Slack/Teams incoming webhook (or Graph API with an Account); (2) DataSet Alert → Webhook action posting JSON to a Slack/Teams webhook (alert-level, not inside the workflow canvas).
- **Gotchas:** No native tile. Teams-in-Domo-Alerts is an open feature request. Slack alert value formatting has known quirks. Third-party iPaaS (n8n/Workato/Make) are alternatives but out of scope for native authoring.
- **Sources:** https://community-forums.domo.com/main/discussion/69148/how-to-link-microsoft-teams-to-workflows, https://community-forums.domo.com/main/discussion/60041/how-to-use-alert-domo-with-slack, https://help.alchemer.com/help/alchemer-workflow-domo-initiator

### notifications

#### Notifications & Alerts integration
*Category: notifications*

- **What it does:** Two directions: (a) a DataSet Alert can be configured to RUN a workflow version as its Action (alert → workflow trigger); (b) inside a workflow, send notifications via the Email user task or the Domo Notifications package, or write to the alerts API.
- **When to use:** Fire a workflow when a data condition is met; or emit alerts/notifications as workflow output.
- **API / JSON representation:** Alerts API (/docs/openapi/product/alerts.yaml), scheduled-reports-api.yaml; alert 'Action' set to a workflow version.
- **Config options:** Alert Action = workflow version; alert parameters can be mapped to workflow start parameters; webhook action on alerts for external targets.
- **Gotchas:** Alert→workflow mapping is configured on the DataSet's Alerts tab, not in the workflow editor. Requires the workflow to be deployed and the right version selected.
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://www.domo.com/docs/llms.txt, https://help.alchemer.com/help/alchemer-workflow-domo-initiator

### flow-control

#### Flow Control — Conditional Logic
*Category: flow-control*

- **What it does:** Applies IF/THEN branching so the workflow continues on a single path based on rules.
- **When to use:** Route the flow based on variable values.
- **API / JSON representation:** Gateway shape; permits multiple outgoing flows.
- **Config options:** Shape name; multiple outgoing flows via nodes; per-branch rules using a Basic rule editor OR Advanced FEEL syntax; combine rules with AND/OR; a Default condition (activates if no other condition is true — best practice to always set one).
- **Gotchas:** Continues on a single matched path; without a default condition an unmatched case can error the workflow.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

#### Flow Control — Parallel Logic
*Category: flow-control*

- **What it does:** Branches into multiple simultaneously-active flows; can also join multiple incoming flows and wait for all to arrive before proceeding.
- **When to use:** Run independent steps concurrently, then synchronize.
- **API / JSON representation:** Gateway shape; multiple incoming and outgoing flows.
- **Config options:** Shape name; add multiple outgoing flows; 'Add Gateway' to add branches. All outgoing flows auto-execute on arrival.
- **Gotchas:** As a join, it blocks until ALL incoming flows reach it.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

#### Flow Control — Wait
*Category: flow-control*

- **What it does:** Delays workflow execution for a specified interval before continuing.
- **When to use:** Insert a pause/delay between steps.
- **API / JSON representation:** Wait shape.
- **Config options:** Duration (variable or custom value). Single outgoing flow only.
- **Gotchas:** One outgoing flow only.
- **Sources:** https://www.domo.com/docs/s/article/000005331

#### Flow Control — End
*Category: flow-control*

- **What it does:** Terminates a workflow branch/execution.
- **When to use:** Mark completion of a path; multiple End shapes allowed for different branches.
- **API / JSON representation:** End shape.
- **Config options:** No outgoing flows; accepts multiple incoming flows.
- **Gotchas:** Multiple End shapes supported.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005331

#### Timer Events (interrupting / non-interrupting)
*Category: flow-control*

- **What it does:** Attach a timer to a shape that listens for task completion and activates an alternate flow on timeout. Interrupting timer cancels the task when the duration is met; Non-interrupting timer lets the task continue and only activates its outgoing flow. Time Cycle supports recurring triggers (indefinite or limited count).
- **When to use:** SLA/timeout handling on user tasks; recurring sub-triggers.
- **API / JSON representation:** Timer event attached to a shape; also present as the 'Timer' tab on function nodes (up to 4 timer events).
- **Config options:** Duration (variable or custom value); Time Cycle (recurring); up to 4 timers per shape; one outgoing flow per timer.
- **Gotchas:** Maximum 4 timers per shape; each timer → exactly one outgoing flow.
- **Sources:** https://www.domo.com/docs/s/article/000005797

### trigger

#### Start / Trigger — Manual
*Category: trigger*

- **What it does:** User-initiated execution via a Start button; the start shape has a single outgoing flow.
- **When to use:** On-demand runs and testing.
- **API / JSON representation:** Start shape (manual).
- **Config options:** Start shape configuration; single outgoing flow only.
- **Gotchas:** Start step permits only one outgoing flow.
- **Sources:** https://www.domo.com/docs/s/article/000005331, https://www.domo.com/docs/s/article/000005797

#### Start / Trigger — Timer / Schedule
*Category: trigger*

- **What it does:** Runs the workflow on a recurring schedule.
- **When to use:** Batch/scheduled automations.
- **API / JSON representation:** Trigger config on the workflow (schedule).
- **Config options:** Every Minute (1/5/15-min, optional time window), Every Hour (optional start/end), Every Day (hour), Every Weekday (Mon–Fri, hour), Every Week (day+hour), Every Month (1st/15th/last day, hour).
- **Gotchas:** Fixed interval presets; not arbitrary cron.
- **Sources:** https://www.domo.com/docs/s/article/000005179

#### Start / Trigger — API (programmatic start)
*Category: trigger*

- **What it does:** Start a deployed workflow programmatically from external systems/scripts/other instances by posting a start message with parameters.
- **When to use:** CI/CD, external apps, cross-instance orchestration.
- **API / JSON representation:** POST https://{instance}.domo.com/api/workflow/v1/instances/message with header X-DOMO-Developer-Token (or bearer JWT); body {messageName:'Start <name>', version:'0.0.1', modelId:'<uuid>', data:{...}}. Alternate: POST /domo/workflow/v1/models/{workflowAlias}/start (used from apps/bricks via domo.post). Response WorkflowInstance {id, modelId, modelName, modelVersion, createdBy/On, updatedBy/On, status}. status enum: null|IN_PROGRESS|CANCELED|COMPLETED|FAILED.
- **Config options:** Provide modelId, version/messageName, and a data object of start parameters (keys match the workflow manifest aliasName values).
- **Gotchas:** modelId is the workflow model UUID; version must match a deployed version. The in-editor 'API trigger' also generates ready-made JS/Python snippets containing a trigger ID.
- **Sources:** https://www.domo.com/docs/api-reference/workflows-api-product/start-a-workflow, https://www.domo.com/docs/openapi/framework/workflows.yaml, https://community-forums.domo.com/main/discussion/64876/having-trouble-running-a-workflow-from-a-domo-brick

#### Start / Trigger — DataSet Alert
*Category: trigger*

- **What it does:** A DataSet alert runs a chosen workflow version when its condition triggers; alert parameters can be passed into the workflow.
- **When to use:** Data-condition-driven automation (thresholds, anomalies).
- **API / JSON representation:** Alerts API; alert Action = workflow version.
- **Config options:** On the DataSet Details → Alerts tab, set the alert Action to a workflow version.
- **Gotchas:** Configured outside the workflow editor.
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://www.domo.com/docs/s/article/000005108

#### Start / Trigger — App Studio / Pro-Code App
*Category: trigger*

- **What it does:** Launch a workflow from a Domo app: an App Studio Workflow widget mapped to a workflow version, or a Pro-code app that starts a workflow via card configuration / the start endpoint.
- **When to use:** User-facing app buttons/forms that kick off automation.
- **API / JSON representation:** domo.post('/domo/workflow/v1/models/{alias}/start', params) from a pro-code app/brick.
- **Config options:** App Studio: add Workflow widget, select workflow version. Pro-code: program the app to call the workflow (card config mapping or domo.post to the start URL).
- **Gotchas:** 404s are common if the alias/model or version is wrong (see community reports).
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://developer.domo.com/portal/81056f6209bfc-start-a-workflow-from-an-app, https://community-forums.domo.com/main/discussion/68592/starting-a-workflow-from-a-domo-app

#### Start / Trigger — Access Request
*Category: trigger*

- **What it does:** Starts a workflow when users request access to a Card, Page, or App; request data can be mapped to workflow start parameters.
- **When to use:** Automate access-request review/approval routing.
- **API / JSON representation:** Access-request trigger type.
- **Config options:** Choose entity type (Card/Page/App) that triggers; optionally map request data to start parameters.
- **Gotchas:** Pairs well with Approvals + General/Email tasks.
- **Sources:** https://www.domo.com/docs/s/article/000005179

### data-model

#### Workflow variable data types (for action input/output mapping)
*Category: data-model*

- **What it does:** The typed variables that action nodes read/write. Knowing these is essential for mapping function inputs/outputs correctly.
- **When to use:** Whenever declaring variables or mapping any action's inputs/outputs.
- **API / JSON representation:** Object types render as 'filled cube' (Defined) vs 'empty cube' (Open) icons. Account passes an ID resolved by the account service and injected over HTTPS; must specify Data Provider and is restricted to accounts created by/shared with the user.
- **Config options:** Text, Number, Decimal, Boolean, Date, Time, Date-Time, Duration, Person, Dataset, Group, Account, Files, Fileset, List (with subtype), Object (Defined — has typed child variables; or Open — arbitrary JSON, ideal for API responses).
- **Gotchas:** Defined Object children can be any type except Object (no nested object children). Open Object is the go-to for holding JSON API payloads from Code Engine functions.
- **Sources:** https://www.domo.com/docs/s/article/000005797, https://www.domo.com/docs/s/article/000005173

### authoring-constraint

#### Workflow versioning & deployment (authoring constraint)
*Category: authoring-constraint*

- **What it does:** Workflows use semantic versioning (major.minor.patch). A deployed version is immutable; to change it you create a new version (the prior version seeds the new one).
- **When to use:** Any programmatic authoring/CI must account for version immutability and re-mapping.
- **API / JSON representation:** modelVersion in WorkflowInstance; version in start message.
- **Config options:** Deploy creates a version; API start must target a deployed version string (e.g. '0.0.1').
- **Gotchas:** Editing requires a new version — you cannot patch a deployed version in place. Requires Manage Workflows grant + Admin/Execute permission. Grants: 'Create Workflows', 'Manage Workflows', 'Create Code Engine Packages'.
- **Sources:** https://www.domo.com/docs/s/article/000005179, https://www.domo.com/docs/s/article/000005173

**Open questions / not fully verified:**

- Domo does not publish a catalog of its built-in Code Engine 'Domo Functions' packages/functions or their exact function names and signatures (confirmed unresolved community request). The exact function names for Buzz post, dataset append, run-dataflow, card/page create, and user/group management must be discovered in-product via the action menu search rather than from docs.
- The precise JSON node/element 'type' strings for workflow model actions/shapes (e.g., how a Query DataSet vs Email vs Conditional node is typed inside a saved workflow model) are not exposed in the public OpenAPI specs — the framework spec only documents start/instance/metrics endpoints, not the model authoring schema. Full programmatic AUTHORING (create a workflow model with nodes) does not appear to be a documented public API; the public Workflow API is start + read instance/metrics only.
- Whether a fully native (no-code) DataSet write/append tile exists in newer Workflow releases, or if it remains Code-Engine-only, could not be confirmed from current docs.
- Exact configuration schema for the AI Agent Task and Domo AI Service Layer nodes (available sub-functions beyond Image-to-Text/Text-Generation/Text-to-SQL) is not documented publicly.
