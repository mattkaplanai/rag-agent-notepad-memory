"""Currency converter tool — Frankfurter API (free, no API key)."""

import json
import urllib.request
import urllib.parse
from langchain_core.tools import tool

FRANKFURTER_BASE = "https://api.frankfurter.dev/v1"


def _fetch_latest_rate(from_currency: str, to_currency: str):
    """Get latest exchange rate from Frankfurter. Returns (rate, date) or (None, error_msg)."""
    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()
    if from_currency == to_currency:
        return 1.0, None
    url = f"{FRANKFURTER_BASE}/latest?base={urllib.parse.quote(from_currency)}&symbols={urllib.parse.quote(to_currency)}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "RefundAgent/1.0 (currency converter)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            err = json.loads(body)
            msg = err.get("message", body[:200])
        except Exception:
            msg = body[:200]
        return None, f"HTTP {e.code}: {msg}"
    except Exception as e:
        return None, str(e)
    rates = data.get("rates") or {}
    if to_currency not in rates:
        return None, f"Currency '{to_currency}' not found. Check /currencies for supported codes."
    return float(rates[to_currency]), data.get("date")


@tool
def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
) -> str:
    """Convert an amount from one currency to another using daily reference rates (Frankfurter/ECB).
    We always respond in USD: if the passenger gives amounts in their currency (e.g. EUR, TRY), use this to convert to USD (to_currency='USD') and then use the USD amount in your analysis and in the decision letter.
    Currencies: 3-letter codes like USD, EUR, TRY, GBP. amount must be a number."""
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return json.dumps({"error": "amount must be a number"})
    if amt < 0:
        return json.dumps({"error": "amount must be non-negative"})
    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()
    if not from_currency or not to_currency:
        return json.dumps({"error": "from_currency and to_currency are required (e.g. USD, EUR)"})
    rate, err = _fetch_latest_rate(from_currency, to_currency)
    if rate is None:
        return json.dumps({"error": err, "from_currency": from_currency, "to_currency": to_currency})
    converted = round(amt * rate, 2)
    return json.dumps({
        "amount": amt,
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate": rate,
        "converted_amount": converted,
        "message": f"{amt} {from_currency} = {converted} {to_currency}",
    })
