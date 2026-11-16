# Actual local verification — 2026-11-17

Frozen report: [benchmarks/mcp-v4.json](benchmarks/mcp-v4.json). Official Python MCP SDK **2.3.0**, Python **3.11.9**, Windows. The actual client/server negotiated protocol **2026-07-28**; the application did not hardcode it.

| Evidence | Measured result |
|---|---:|
| Unit tests | 20 passed, no skips in this run |
| Protocol/workflow assertions in the integration scenario | 57/57 passed |
| Actual stdio tool calls | 40 |
| Advertised MCP tools | 10 |
| Concrete policy resource / issue resource template / prompt | Discovered and read/rendered |
| Domain events after the protocol scenario | 2, for two different approved actions |
| UI retry of one approved transition | Version 2, exactly one event |

The assertions are checks within a small authored scenario, not 57 independent security cases. The report records the 39 primary-connection tool results, with receipt/absolute-path redactions; the fortieth call is the reconnect replay checked separately. Resource/prompt/metadata calls are additional protocol operations, not included in the tool-call count.

## Successful paths

- Real SDK client initialization, tool schema discovery and structured tool results through a separate stdio process.
- Three document pages covered all six alpha files without duplicates; issue keyset pagination covered the three alpha records.
- Lexical document search, exact line evidence, byte-level source SHA-256 and explicit untrusted-data labels.
- Concrete policy resource, parameterized issue resource and triage prompt template retrieval.
- Pending proposal and local approval each left the issue unchanged. Only applying the approved receipt changed its status/version.
- Reusing an idempotency key with the same payload returned the original proposal. Applying an approved action again returned `replayed: true` without another event.
- A new client reconnected after the first apply result was deliberately discarded and recovered the committed result without another update.

## Denied paths

The actual MCP error channel rejected parent/absolute/device-style and alternate-stream document paths, beta issue access, oversized/wrong-type page arguments, a tampered cursor, cursor reuse under a different search query, invalid transition arguments, unknown nested request fields, changed-payload key reuse, unapproved/rejected/expired action application, and a stale approved issue version.

The expiry condition was injected by changing the timestamp in an isolated verification database; it was not a ten-minute live wait. There was no automated LLM deciding what to call. The adversarial document text was returned as labelled data and did not cause another tool call or state transition; that does not establish resistance to an LLM following malicious text.

## State consistency tests

Eight concurrent local retries for one approved action produced one non-replayed result, one issue version increment and one event. A SQLite trigger injected an error after the issue/event update but before the result record could finish: the whole transaction rolled back, and a later retry applied once after removing that fixture trigger. This is a transactional interruption test, not an observed power-loss or arbitrary process-crash recovery test.

A real filesystem symlink escape was denied on the verification machine, and scanning skipped that link. CRLF and LF source handling, stale document snapshots, pagination integrity, size/range limits, rejected actions and payload-hash mismatches were also checked. The application still assumes a trusted local owner and does not comprehensively harden against hostile concurrent filesystem swaps.

## UI verification

Streamlit's application runner used the actual SDK client and MCP subprocesses against an isolated SQLite database. It discovered ten tools, searched/read `retries.md`, reused one proposal on duplicate clicks, required the action-bound review checkbox, approved without applying, applied once and replayed once. The final issue was `in_progress`, version 2, with one event.

Only the database path was isolated via environment configuration; no fake tool/client engine replaced the protocol. This does not verify live-browser layout, an external chat host or an LLM agent. The UI is a custom client rather than the upstream Node MCP Inspector.

## Interpretation

These results demonstrate scoped local tool behavior and retry/review mechanics. They do not establish authentication, real tenant isolation, tamper-proof audit storage, production throughput, public deployment or universal MCP-host compatibility. A process with owner-level access to SQLite/code/reviewer functions remains trusted. No provider API or model-quality benchmark is part of this project.
