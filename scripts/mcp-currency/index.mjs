#!/usr/bin/env node
/**
 * MCP Currency Converter — Frankfurter API (no API key).
 * Run: node index.mjs (stdio). Use from Cursor via .cursor/mcp.json.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const FRANKFURTER_BASE = "https://api.frankfurter.dev/v1";

async function fetchRate(fromCurrency, toCurrency) {
  const from = String(fromCurrency).trim().toUpperCase();
  const to = String(toCurrency).trim().toUpperCase();
  if (from === to) return { rate: 1, date: null };
  const url = `${FRANKFURTER_BASE}/latest?base=${encodeURIComponent(from)}&symbols=${encodeURIComponent(to)}`;
  const res = await fetch(url, {
    headers: { "User-Agent": "RefundAgent-MCP/1.0 (currency)" },
  });
  if (!res.ok) {
    const t = await res.text();
    let msg = t.slice(0, 200);
    try {
      const j = JSON.parse(t);
      if (j.message) msg = j.message;
    } catch (_) {}
    throw new Error(`HTTP ${res.status}: ${msg}`);
  }
  const data = await res.json();
  const rates = data.rates || {};
  if (!(to in rates)) throw new Error(`Currency '${to}' not found. Use 3-letter codes (USD, EUR, TRY, etc.).`);
  return { rate: Number(rates[to]), date: data.date || null };
}

const server = new McpServer({
  name: "currency-converter",
  version: "1.0.0",
  capabilities: { tools: {} },
});

server.tool(
  "convert_currency",
  "Convert an amount from one currency to another (Frankfurter/ECB daily rates). Use 3-letter codes: USD, EUR, TRY, GBP, etc. We often respond in USD.",
  {
    amount: z.number().nonnegative(),
    from_currency: z.string().min(3).max(3),
    to_currency: z.string().min(3).max(3),
  },
  async ({ amount, from_currency, to_currency }) => {
    try {
      const { rate, date } = await fetchRate(from_currency, to_currency);
      const converted = Math.round(amount * rate * 100) / 100;
      const text = JSON.stringify(
        {
          amount,
          from_currency: from_currency.toUpperCase(),
          to_currency: to_currency.toUpperCase(),
          rate,
          converted_amount: converted,
          date,
          message: `${amount} ${from_currency.toUpperCase()} = ${converted} ${to_currency.toUpperCase()}`,
        },
        null,
        2
      );
      return { content: [{ type: "text", text }] };
    } catch (err) {
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({ error: err.message || String(err) }),
          },
        ],
        isError: true,
      };
    }
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
