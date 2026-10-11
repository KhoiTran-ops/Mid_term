"""Extend hand-curated aliases with the complete local issuer universe."""
from copy import deepcopy
import re
import sqlite3


def universe_entities(settings, base):
    entities=deepcopy(base)
    if not settings.market_database.is_file():return entities
    with sqlite3.connect(settings.market_database,timeout=30) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='instruments'").fetchone():return entities
        rows=db.execute('SELECT symbol,company_name FROM instruments ORDER BY symbol').fetchall()
    for symbol,name in rows:
        if not re.fullmatch(r'[A-Z0-9]{2,12}',symbol):continue
        aliases=entities['companies'].setdefault(symbol,[])
        stripped=re.sub(r'^(?:CTCP|CT TNHH|Công ty cổ phần|Công ty CP|Ngân hàng TMCP)\s+','',name or '',flags=re.I).strip()
        for alias in (symbol,name,stripped if len(stripped.split())>=2 else None):
            if alias and alias not in aliases:aliases.append(alias)
    return entities
