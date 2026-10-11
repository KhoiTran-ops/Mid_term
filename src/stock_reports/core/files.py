"""Atomic JSON publication resilient to short Windows reader/antivirus locks."""
import json
import os
from pathlib import Path
import time
import uuid


def atomic_json(path, payload):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(8):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == 7: raise
                time.sleep(min(.05 * 2 ** attempt, 1))
    finally:
        temporary.unlink(missing_ok=True)
