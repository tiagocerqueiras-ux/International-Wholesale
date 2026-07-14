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


# Palavras a ignorar no matching (formas jurídicas / genéricas)
_STOP = {
    "SA", "LDA", "LD", "LTD", "LTDA", "UNIPESSOAL", "SARL", "SL", "SRL", "EOOD",
    "GMBH", "INC", "SPA", "LIMITADA", "E", "DE", "DO", "DA", "DOS", "DAS",
    "COMERCIAL", "SOCIEDADE", "INTERNACIONAL", "COMERCIO", "IMPORTACAO",
    "EXPORTACAO", "GROUP", "TECHNOLOGIE", "TECHNOLOGIES", "S",
}


def _tok(ncn: str) -> set:
    """Tokens significativos de um nome já normalizado."""
    return set(t for t in ncn.split() if t not in _STOP and len(t) >= 3)


def _matches(cn: str, rcn: str) -> bool:
    """cn e rcn já normalizados."""
    if not cn or not rcn:
        return False
    if cn == rcn:
        return True
    ta, tb = _tok(cn), _tok(rcn)
    if ta and tb:
        small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        if small.issubset(big):      # tokens do nome mais curto ⊆ do mais longo
            return True
    return len(cn) >= 6 and (cn in rcn or rcn in cn)


def name_matches(a, b) -> bool:
    """Match de nomes de cliente (normaliza + tokens)."""
    return _matches(norm(a), norm(b))


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
