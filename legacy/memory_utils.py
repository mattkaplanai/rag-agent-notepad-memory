"""
Notepad ve uzun süreli bellek için dosya okuma/yazma.
"""
import json
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent
NOTEPAD_FILE = PROJECT_ROOT / "notepad.txt"
LONG_MEMORY_FILE = PROJECT_ROOT / "long_memory.json"


def read_notepad() -> str:
    """Notepad dosyasının içeriğini döner."""
    if not NOTEPAD_FILE.exists():
        return ""
    try:
        return NOTEPAD_FILE.read_text(encoding="utf-8")
    except Exception:
        return ""


def write_notepad(content: str, mode: str = "overwrite") -> str:
    """Notepad'e yazar. mode: 'overwrite' veya 'append'."""
    NOTEPAD_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        if mode == "append":
            current = read_notepad()
            new_content = (current + "\n" + content).strip()
        else:
            new_content = content
        NOTEPAD_FILE.write_text(new_content, encoding="utf-8")
        return "OK"
    except Exception as e:
        return str(e)


def load_long_memory() -> dict:
    """Uzun süreli belleği yükler. {'facts': [{'key': ..., 'value': ...}]}."""
    if not LONG_MEMORY_FILE.exists():
        return {"facts": []}
    try:
        data = json.loads(LONG_MEMORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and "facts" in data else {"facts": []}
    except Exception:
        return {"facts": []}


def save_long_memory(data: dict) -> None:
    """Uzun süreli belleği kaydeder."""
    LONG_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    LONG_MEMORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def remember_fact(key: str, value: str) -> str:
    """Bir bilgiyi uzun süreli belleğe ekler veya günceller."""
    data = load_long_memory()
    facts = {f["key"]: f["value"] for f in data["facts"]}
    facts[key.strip()] = value.strip()
    data["facts"] = [{"key": k, "value": v} for k, v in facts.items()]
    save_long_memory(data)
    return "Kaydedildi."


def recall_fact(key: Optional[str] = None) -> str:
    """Tek bir anahtar veya tüm belleği döner. key None ise tümü."""
    data = load_long_memory()
    facts = data.get("facts", [])
    if not facts:
        return "Uzun süreli bellekte henüz bilgi yok."
    if key:
        key = key.strip()
        for f in facts:
            if f.get("key") == key:
                return f.get("value", "")
        return f"'{key}' için kayıt bulunamadı."
    return "\n".join(f"- {f['key']}: {f['value']}" for f in facts)
