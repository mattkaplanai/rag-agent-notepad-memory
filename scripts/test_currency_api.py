#!/usr/bin/env python3
"""
Test script for currency converter (Frankfurter API — free, no API key).
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from app.tools.currency import convert_currency

def main():
    print("Currency converter test (Frankfurter API)")
    print()

    # 100 USD -> EUR
    print("1) convert_currency(100, 'USD', 'EUR')")
    out = convert_currency.invoke({"amount": 100, "from_currency": "USD", "to_currency": "EUR"})
    print("   ", out)
    print()

    # 50 EUR -> TRY
    print("2) convert_currency(50, 'EUR', 'TRY')")
    out = convert_currency.invoke({"amount": 50, "from_currency": "EUR", "to_currency": "TRY"})
    print("   ", out)
    print()

    # Same currency
    print("3) convert_currency(10, 'USD', 'USD')")
    out = convert_currency.invoke({"amount": 10, "from_currency": "USD", "to_currency": "USD"})
    print("   ", out)
    print()

    print("Done. No API key required (Frankfurter is free).")

if __name__ == "__main__":
    main()
