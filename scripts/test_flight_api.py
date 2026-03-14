#!/usr/bin/env python3
"""
Test script for flight status APIs (AviationStack).
Refund kararı için: gecikme/iptal bilgisini doğrulamak.
"""
import os
import sys
from pathlib import Path

# project root
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

try:
    from dotenv import load_dotenv
    load_dotenv(root / ".env")
except ImportError:
    pass

import urllib.request
import urllib.parse
import json


def aviationstack_flights(access_key, flight_iata=None, flight_date=None):
    """AviationStack v1/flights - real-time veya historical."""
    base = "https://api.aviationstack.com/v1/flights"
    params = {}
    if access_key:
        params["access_key"] = access_key
    if flight_iata:
        params["flight_iata"] = flight_iata
    if flight_date:
        params["flight_date"] = flight_date
    params.setdefault("limit", "3")
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main():
    key = (
        os.environ.get("AVIATIONSTACK_ACCESS_KEY")
        or os.environ.get("AVIATIONSTACK_ACCESS")
        or os.environ.get("AVIATIONSTACK_API_KEY")
    )
    print("AviationStack API test")
    print("  Endpoint: https://api.aviationstack.com/v1/flights")
    print("  Key set:", bool(key))
    print()

    if not key:
        print("Key yok - API'ye istek atıp endpoint'in çalıştığını doğruluyoruz (401 beklenir)...")
        try:
            aviationstack_flights(None)
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            print(f"  HTTP {e.code}: {e.reason}")
            try:
                print("  Body:", json.dumps(json.loads(body), indent=2, ensure_ascii=False))
            except Exception:
                print("  Body:", body[:500])
            if e.code == 401:
                print("\n  -> Endpoint erişilebilir; API key gerekli. Ücretsiz key: https://aviationstack.com/signup/free")
            return
        except Exception as e:
            print("  Hata:", e)
            return

    # İsteğe bağlı: tek uçuş kodu (örn. TK123)
    flight_arg = sys.argv[1].strip().upper() if len(sys.argv) > 1 else None
    if flight_arg:
        print("Gerçek istek (flight_iata={})...".format(flight_arg))
    else:
        print("Gerçek istek (real-time flights, limit=3)...")
    try:
        data = aviationstack_flights(key, flight_iata=flight_arg)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"  HTTP {e.code}: {body[:400]}")
        return
    except Exception as e:
        print("  Hata:", e)
        return

    error = data.get("error")
    if error:
        print("  API error:", error)
        return

    pagination = data.get("pagination", {})
    results = data.get("data") or []
    print(f"  Toplam: {pagination.get('total')}, dönen: {len(results)}")
    for i, f in enumerate(results[:5], 1):
        status = f.get("flight_status")
        dep = f.get("departure") or {}
        arr = f.get("arrival") or {}
        delay_dep = dep.get("delay")
        delay_arr = arr.get("delay")
        flight_iata = (f.get("flight") or {}).get("iata") or "?"
        airline = (f.get("airline") or {}).get("name") or "?"
        print(f"  [{i}] {flight_iata} ({airline}) -> {status}")
        print(f"      Departure delay: {delay_dep} min, Arrival delay: {delay_arr} min")
        if status == "cancelled":
            print("      *** İPTAL ***")
    print("\n  Refund kararı için: flight_status in (cancelled, incident, diverted), delay_dep/delay_arr kullanılabilir.")


if __name__ == "__main__":
    main()
