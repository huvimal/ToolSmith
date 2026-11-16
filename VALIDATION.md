# Verification scope

Verified locally on 2026-11-17. Installed package versions are recorded in `requirements-lock-windows.txt`.

Completed:

- Dependency consistency: `python -m pip check` passed.
- 20 unit tests passed without skips in the local run; symlink availability can differ on another OS/account.
- Actual official SDK v2 stdio client/server integration: 57 protocol/workflow assertions and 40 tool calls, plus resource/prompt/metadata operations.
- Actual structured output contract. Return annotations use explicit `dict[str, Any]` with structured output enabled; the installed SDK did not infer structured output for bare `dict` in the initial probe.
- Denied scope/schema/approval/version paths returned MCP tool errors; policy errors are deliberately translated to SDK `ToolError`, rather than pretending they succeeded.
- Real UI-to-client-to-server-to-SQLite workflow and retry checks, with a temporary DB path but no mocked tool engine.
- Runtime proof used separate disposable databases, preserving the user's interactive fixture state.

Evidence:

- [benchmarks/mcp-v4.json](benchmarks/mcp-v4.json): frozen final protocol report, fixture hashes, redacted arguments, call results and assertions.
- `reports/ui-v1.json`: actual UI runner evidence.
- `reports/mcp-v4.json`: local copy of the public frozen report.
- `tests/`: unit checks including concurrency, transaction failure injection and real symlink denial when allowed by the OS.

Earlier diagnostic reports remain local under ignored `reports/`; the frozen public report uses the final structured-output/policy-error behavior. Fixture content was not edited to make denial checks pass. `.gitattributes` keeps tracked fixture text at LF for stable source hashes across normal Git checkouts; actual reads preserve source bytes and CRLF test fixtures are checked separately.

Not verified: a live browser's visual layout, Claude Desktop/Codex/ChatGPT installation, an LLM agent deciding tool calls, public HTTP transport, OAuth, Docker deployment, hosted GitHub Actions, production retention/rate limiting or hostile host/filesystem isolation. Approval is a separate trusted local workflow, not authentication.

## Recheck

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 verify_mcp.py --output reports/my-new-run.json
.\.venv\Scripts\python.exe -X utf8 verify_ui.py
```

Use a new protocol report filename. Verification does not reset the interactive SQLite database. The UI test evidence file may be updated; preserve it separately if comparing application versions.
