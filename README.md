# playwright-python-mcp

Python-native port of the official Playwright MCP server.

The public MCP surface tracks upstream Playwright MCP tool names, capability names, schemas, and browser behavior. The intentional divergence is generated code snippets: this port emits Python Playwright syntax such as:

```python
await page.get_by_role("button", name="Submit").click()
```

instead of upstream JavaScript snippets.

## Install And Run

From a published package:

```bash
uvx playwright-python-mcp --headless
```

From this checkout:

```bash
uv run playwright-python-mcp --headless
```

Python module execution is also supported:

```bash
uv run python -m playwright_python_mcp --headless
```

Install browser binaries when needed:

```bash
uv run playwright-python-mcp install-browser chrome
```

## Common Options

```bash
uv run playwright-python-mcp \
  --browser=chrome \
  --headless \
  --caps=vision,pdf,storage,testing,config \
  --output-dir=.playwright-mcp
```

Supported configuration sources follow upstream merge order:

1. Defaults.
2. JSON or INI config file from `--config` or `PLAYWRIGHT_MCP_CONFIG`.
3. `PLAYWRIGHT_MCP_*` environment variables.
4. CLI flags.

Examples:

```bash
PLAYWRIGHT_MCP_TIMEOUT_NAVIGATION=45000 \
uv run playwright-python-mcp --config=playwright-mcp.ini --timeout-action=10000
```

```ini
capabilities = config,storage
console.level = error
timeouts.action = 10000
timeouts.navigation = 45000
browser.contextOptions.viewport = 1280x720
```

## Public Interfaces

- Import package: `playwright_python_mcp`
- Module execution: `python -m playwright_python_mcp`
- Console script: `playwright-python-mcp`
- MCP transport: stdio by default
- Tool registration: generated from the Python tool registry, not hardcoded decorators

## Development

Quality gates:

```bash
uv run ruff check .
uv run ty check
uv run mypy .
uv run pytest
```

Adapted upstream conformance tests:

```bash
cd tests/conformance/upstream
npx playwright test --workers=10
```

The conformance specs are copied from upstream Playwright MCP where practical and adapted only for this Python-native port's intentional snippet syntax divergence or fixture limitations.

## Dependency Policy

- Python: `>=3.12`
- `playwright>=1.61.0`
- `fastmcp>=3.4.2`

FastMCP is used as the MCP adapter layer only. Browser behavior and tool semantics live in `src/playwright_python_mcp/backend`.

## Upstream

See [UPSTREAM.md](UPSTREAM.md) for pinned upstream SHAs and source files used by this port.
