import json
from dataclasses import dataclass

@dataclass(frozen=True)
class Caption:
    segment: int
    revision: int
    source_ts: float
    final: bool
    text: str
    wire: str  # Pre-encoded compact JSON string

def parse(raw: str | bytes) -> dict | None:
    """Safely parse incoming raw bytes/strings without crashing."""
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None

def caption_from(msg: dict) -> Caption | None:
    """Validates required fields and drops unknown ones."""
    if not isinstance(msg, dict) or msg.get("type") != "CAPTION_UPDATE":
        return None
        
    try:
        segment = int(msg["segment"])
        revision = int(msg["revision"])
        source_ts = float(msg["source_ts"])
        final = bool(msg.get("final", False))
        text = str(msg["text"])
        
        # Encode once: strip spaces to save bandwidth
        wire_dict = {
            "type": "CAPTION_UPDATE",
            "segment": segment,
            "revision": revision,
            "source_ts": source_ts,
            "final": final,
            "text": text
        }
        wire = json.dumps(wire_dict, separators=(",", ":"))
        
        return Caption(segment, revision, source_ts, final, text, wire)
    except (KeyError, ValueError, TypeError):
        # Ignore malformed payloads silently
        return None