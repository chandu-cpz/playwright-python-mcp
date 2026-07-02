# Upstream References

This repository is a Python-native port of the official Playwright MCP.

Pinned local upstream snapshots used for the current port:

- Playwright monorepo: `microsoft/playwright@50d4a6e6bc5b16ed87b1a74b7ec84c4fe7adf3e1`
- Playwright MCP wrapper repo: `microsoft/playwright-mcp@36ec986b8b1fc6b4d11f2b6971147755e1b0bc84`

Primary implementation references:

- `packages/playwright-core/src/tools/mcp/index.ts`
- `packages/playwright-core/src/tools/mcp/program.ts`
- `packages/playwright-core/src/tools/mcp/config.ts`
- `packages/playwright-core/src/tools/backend/*.ts`
- `packages/playwright-core/src/tools/utils/mcp/server.ts`
- `tests/mcp/*.spec.ts`

Port policy:

- Preserve official MCP tool names, capabilities, gating, schemas, and runtime semantics where Python Playwright can support them.
- Runtime execution uses Python Playwright APIs.
- Generated response snippets intentionally use Python Playwright syntax, not JavaScript syntax.
- Keep FastMCP as a thin transport/registration adapter; core behavior belongs in normal Python modules.
