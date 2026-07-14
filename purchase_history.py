"""
purchase_history.py — referência de preço por cliente (African Markets)
=======================================================================
Lê data/purchase_history.json (gerado por import_purchase_history.py) e
responde ao histórico de compras de um cliente para um SKU, para dar
consistência de preços na construção da proposta.
"""
import re
import json
import unicodedata
from pathlib import Path

_CACHE = None


def _load() -> dict:
    global _CACHE
    if _CACHE is None:
        p = Path(__file__).parent / "data" / "purchase_history.json"
        try:
            _CACHE = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {"records": [], "clients": []}
    return _CACHE


def norm(s: str) -> str:
    s = str(s or "").strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _matches(cn: str, rcn: str) -> bool:
    if not cn or not rcn:
        return False
    if cn == rcn:
        return True
    # tolerância a truncagem/variantes — evita matches curtos demais
    return len(cn) >= 6 and (cn in rcn or rcn in cn)


def client_sku_history(client: str, sku: str) -> list:
    """Compras deste cliente para este SKU (mais recente primeiro)."""
    data = _load()
    cn = norm(client)
    sku = str(sku).strip()
    recs = [r for r in data.get("records", [])
            if r.get("sku") == sku and _matches(cn, r.get("client_norm", ""))]
    recs.sort(key=lambda r: r.get("date", ""), reverse=True)
    return recs


def last_purchase(client: str, sku: str, concluded_first: bool = True) -> dict | None:
    """Referência de preço: {price, date, qty, n, status} ou None."""
    recs = client_sku_history(client, sku)
    if not recs:
        return None
    pool = recs
    if concluded_first:
        conc = [r for r in recs if "CONCLU" in r.get("status", "")]
        pool = conc or recs
    r0 = pool[0]
    return {"price": r0.get("price"), "date": r0.get("date", ""),
            "qty": r0.get("qty"), "n": len(recs), "status": r0.get("status", "")}


def has_client(client: str) -> bool:
    cn = norm(client)
    return any(_matches(cn, c) for c in _load().get("clients", []))
