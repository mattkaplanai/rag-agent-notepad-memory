"""
Decision Cache: Two-level caching to minimize LLM costs.

Level 1 — Exact match:  Hash all form inputs. If identical case was seen
                         before, return the cached decision instantly ($0).

Level 2 — Semantic match: Embed the description text and compare cosine
                          similarity to cached descriptions. If similarity
                          exceeds the threshold, reuse the cached decision
                          (costs only 1 embedding call instead of full LLM).

Cache is persisted to disk as JSON (for fast lookups with embeddings)
and also exported to an Excel spreadsheet (for human review).
"""

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_FILE = PROJECT_ROOT / "decision_cache.json"
EXCEL_FILE = PROJECT_ROOT / "decision_log.xlsx"

SEMANTIC_THRESHOLD = 0.90


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def _hash_inputs(
    case_type: str,
    flight_type: str,
    ticket_type: str,
    payment_method: str,
    accepted_alternative: str,
    description: str,
) -> str:
    raw = "|".join([
        case_type.strip().lower(),
        flight_type.strip().lower(),
        ticket_type.strip().lower(),
        payment_method.strip().lower(),
        accepted_alternative.strip().lower(),
        description.strip().lower(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_embedding(text: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI()
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
    )
    return response.data[0].embedding


class DecisionCache:
    """Two-level cache: exact hash match → semantic similarity → LLM."""

    def __init__(self, cache_path: Path = CACHE_FILE):
        self.cache_path = cache_path
        self.entries: list[dict] = []
        self._load()

    def _load(self):
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self.entries = data if isinstance(data, list) else []
                print(f"[CACHE] Loaded {len(self.entries)} cached decisions.")
            except Exception:
                self.entries = []
        else:
            self.entries = []

    def _save(self):
        self.cache_path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._export_excel()

    def _export_excel(self):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = Workbook()
        ws = wb.active
        ws.title = "Refund Decisions"

        headers = [
            "No", "Date/Time", "Case Type", "Flight Type", "Ticket Type",
            "Payment Method", "Description", "Decision", "Confidence",
            "Analysis Steps", "Reasons", "Applicable Regulations",
            "Refund Type", "Refund Payment", "Refund Timeline",
            "Passenger Action Items",
        ]

        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="2E5090", end_color="2E5090", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
            cell.border = thin_border

        decision_fills = {
            "APPROVED": PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
            "DENIED": PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
            "PARTIAL": PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
        }

        for row_idx, entry in enumerate(self.entries, 2):
            result = entry.get("result", {})
            refund = result.get("refund_details") or {}
            ts = entry.get("timestamp", 0)
            dt_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""

            row_data = [
                row_idx - 1,
                dt_str,
                entry.get("case_type", ""),
                entry.get("flight_type", ""),
                entry.get("ticket_type", ""),
                entry.get("payment_method", ""),
                entry.get("description_preview", ""),
                result.get("decision", ""),
                result.get("confidence", ""),
                "\n".join(result.get("analysis_steps", [])),
                "\n".join(result.get("reasons", [])),
                "\n".join(result.get("applicable_regulations", [])),
                refund.get("refund_type", "N/A"),
                refund.get("payment_method", "N/A"),
                refund.get("timeline", "N/A"),
                "\n".join(result.get("passenger_action_items", [])),
            ]

            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                cell.border = thin_border

            decision_cell = ws.cell(row=row_idx, column=8)
            fill = decision_fills.get(result.get("decision", ""))
            if fill:
                decision_cell.fill = fill
                decision_cell.font = Font(bold=True)

        col_widths = [5, 18, 22, 18, 15, 15, 40, 12, 12, 50, 40, 40, 30, 25, 25, 40]
        for col_idx, width in enumerate(col_widths, 1):
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width

        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"

        wb.save(str(EXCEL_FILE))
        print(f"[CACHE] 📊 Excel log updated: {EXCEL_FILE.name} ({len(self.entries)} rows)")

    def lookup(
        self,
        case_type: str,
        flight_type: str,
        ticket_type: str,
        payment_method: str,
        accepted_alternative: str,
        description: str,
    ) -> tuple[Optional[dict], str]:
        """
        Look up a cached decision.

        Returns:
            (result_dict, cache_status)
            cache_status is one of: "exact_hit", "semantic_hit", "miss"
        """
        input_hash = _hash_inputs(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        # Level 1: exact match
        for entry in self.entries:
            if entry.get("hash") == input_hash:
                print(f"[CACHE] ✅ Exact hit — returning cached decision (saved full LLM call)")
                return entry["result"], "exact_hit"

        # Level 2: semantic similarity on description
        if not description.strip():
            return None, "miss"

        query_embedding = _get_embedding(description)

        best_sim = 0.0
        best_entry = None
        for entry in self.entries:
            emb = entry.get("embedding")
            if not emb:
                continue
            sim = _cosine_similarity(query_embedding, emb)
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry and best_sim >= SEMANTIC_THRESHOLD:
            print(f"[CACHE] 🔍 Semantic hit — similarity {best_sim:.3f} ≥ {SEMANTIC_THRESHOLD} (saved LLM call)")
            return best_entry["result"], "semantic_hit"

        print(f"[CACHE] ❌ Miss — best similarity {best_sim:.3f} < {SEMANTIC_THRESHOLD}")
        return None, "miss"

    def store(
        self,
        case_type: str,
        flight_type: str,
        ticket_type: str,
        payment_method: str,
        accepted_alternative: str,
        description: str,
        result: dict,
    ):
        """Store a new decision in the cache."""
        input_hash = _hash_inputs(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        embedding = _get_embedding(description) if description.strip() else []

        entry = {
            "hash": input_hash,
            "case_type": case_type,
            "flight_type": flight_type,
            "ticket_type": ticket_type,
            "payment_method": payment_method,
            "accepted_alternative": accepted_alternative,
            "description_preview": description[:200],
            "embedding": embedding,
            "result": result,
            "timestamp": time.time(),
        }
        self.entries.append(entry)
        self._save()
        print(f"[CACHE] 💾 Stored decision — cache now has {len(self.entries)} entries.")

    @property
    def stats(self) -> dict:
        return {
            "total_entries": len(self.entries),
            "cache_file": str(self.cache_path),
        }

    def clear(self):
        self.entries = []
        self._save()
        if EXCEL_FILE.exists():
            EXCEL_FILE.unlink()
        print("[CACHE] 🗑️ Cache and Excel log cleared.")
