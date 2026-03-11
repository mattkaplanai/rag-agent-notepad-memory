# MCP Currency Converter

Small MCP server for currency conversion using the [Frankfurter API](https://www.frankfurter.app/) (no API key).

Used by Cursor via `.cursor/mcp.json`. Provides one tool:

- **convert_currency** — `amount`, `from_currency`, `to_currency` (3-letter codes: USD, EUR, TRY, etc.)

## Run locally

```bash
cd scripts/mcp-currency
npm install
node index.mjs
```

(Runs on stdio; Cursor starts it automatically when the MCP is enabled.)

## Dependencies

- Node.js 18+
- `@modelcontextprotocol/sdk`, `zod` (see package.json)
