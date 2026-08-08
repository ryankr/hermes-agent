# Memory observability — implementation plan

## Goal
Add local-only, opt-in-by-use measurement for the existing memory stack. The report must measure A–D without sending analytics externally or altering the model prompt/tool schema.

## Scope
Extend the existing `hermes insights` command and `InsightsEngine`; add a `hermes memory evaluate` subcommand for explicit human outcome labels.

### A. Coverage
- Detect session use of memory-retrieval paths: built-in `memory`, mem0 MCP recall/list, `session_search`, and Markdown-vault reads (file-tool calls under configured memory roots).
- Report sessions and calls by source, plus the percentage of in-scope sessions that used each source.

### B. Precision
- Persist an optional reviewer label per session: `used_verified`, `used_but_stale`, `not_used_irrelevant`, `wrong_or_conflicting`, or `missing`.
- Report labelled counts, precision, and stale/conflict rate. Never infer these labels from model text.

### C. Outcome
- Persist an optional reviewer outcome: `helped`, `neutral`, `hindered`; plus recheck level: `none`, `ssot_check`, `correction`.
- Report label coverage and outcome distribution; do not claim causality from unlabelled sessions.

### D. Cost / latency
- Compare memory-used vs no-memory sessions observationally: median elapsed duration, input/output/cache tokens, and tool calls per session.
- Display a clear non-causal warning because task complexity is uncontrolled.

## Data model and privacy
- Store only local, append/replace evaluator metadata in a `memory_evaluations` table in the existing `state.db`.
- Link by `session_id`; store no recalled text, prompts, tool arguments, model output, remote identifiers, or external telemetry.
- Use `ON DELETE CASCADE` so removing a session removes its evaluation.

## CLI
```text
hermes memory evaluate SESSION_ID \
  --retrieval used_verified \
  --outcome helped \
  --recheck ssot_check \
  [--note "optional short reviewer note"]

hermes insights --days 30 [--source slack]
```
`hermes memory evaluate` is idempotent per session: rerunning updates the one local evaluation record.

## Implementation steps
1. Add schema/table and `SessionDB` evaluation CRUD APIs.
2. Add `MemoryObservabilityEngine` that parses persisted assistant tool-call JSON and computes coverage, evaluator-label quality/outcomes, and observational cohort comparisons.
3. Integrate a Memory Observability section into `InsightsEngine.generate()` and terminal formatting.
4. Add parser and handler for `hermes memory evaluate`.
5. Add unit tests (schema CRUD, extraction and aggregation, report formatting) and a temp-`HERMES_HOME` CLI integration test.
6. Run focused tests, then the relevant broader insights/CLI suite. Exercise the installed local CLI against the real state DB read-only in reporting mode.

## Acceptance criteria
- `hermes insights` shows an empty-safe Memory Observability section.
- Data is derived from existing local transcripts and explicit labels only; no runtime prompt mutation, proxy, provider change, or outbound telemetry is added.
- Evaluation rejects unknown session IDs and invalid enum values.
- Repeated evaluation updates rather than duplicates rows.
- Cohort reports distinguish observational comparison from causal outcome claims.
