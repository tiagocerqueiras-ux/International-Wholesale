"""
stock_whs.py — Stocks diários por armazém (Pendentes África*.xlsb, tab STK WHs)
===============================================================================
OPT-IN: só é usado quando config.DAILY_STOCKS_ENABLED=1. Por defeito a app usa a
coluna "STOCK DISPONÍVEL" do próprio simulador (decisão 2026-09-03: o ficheiro
STK WHs esteve 6 semanas parado — renomeado pelo BI e sincronizado noutra pasta —
sem que a app desse por isso, servindo stocks errados).

Quando ligado: lê o ficheiro SharePoint "Pendentes África*.xlsb" mais recente
(site STOCK & SPACE MANAGEMENT, sincronizado via OneDrive), tab STK WHs, e devolve
por SKU e armazém: disponível = STOCK_ON_HAND − TSF_RESERVED_QTY − NON_SELLABLE_QTY.

Cache em .cache/stock_whs.json com gate por (ficheiro, mtime) — o xlsb tem ~77MB e
a leitura demora ~1-2 min.
"""
import json
from pathlib import Path

_ROOTS = [
    Path.home() / "OneDrive - Worten" / "STOCK & SPACE MANAGEMENT - África",
    Path.home() / "Worten" / "STOCK & SPACE MANAGEMENT - África",
]
# O BI muda o nome quando republica (Pendentes África.xlsb → Pendentes África2.xlsb)
# e cada raiz de sync pode ficar com uma cópia antiga parada — escolher sempre o
# ficheiro MAIS RECENTE por mtime em qualquer das raízes.
_PATTERN = "Pendentes África*.xlsb"
CACHE = Path(__file__).resolve().parent / ".cache" / "stock_whs.json"
SHEET = "STK WHs"


def find_file():
    best = None
    for root in _ROOTS:
        try:
            for c in root.glob(_PATTERN):
                if c.name.startswith("~$"):
                    continue
                if best is None or c.stat().st_mtime > best.stat().st_mtime:
                    best = c
        except Exception:
            continue
    return best


def _norm_sku(v) -> str:
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def build(force: bool = False) -> dict:
    """{sku: {"701": disp, "708": disp, "2928": disp, ...}} — vazio se indisponível."""
    src = find_file()
    if src is None:
        return {}
    # cache válida? (mesmo ficheiro E mesma versão)
    if CACHE.exists() and not force:
        try:
            payload = json.loads(CACHE.read_text(encoding="utf-8"))
            if payload.get("_mtime") == src.stat().st_mtime \
                    and payload.get("_src", str(src)) == str(src):
                return payload.get("stocks", {})
        except Exception:
            pass
    try:
        from pyxlsb import open_workbook
    except ImportError:
        print("[stock_whs] pyxlsb não instalado — sem stocks diários.")
        return {}
    stocks: dict = {}
    try:
        with open_workbook(str(src)) as wb:
            with wb.get_sheet(SHEET) as ws:
                hdr = None
                for row in ws.rows():
                    vals = [c.v for c in row]
                    if hdr is None:
                        hdr = {str(v).strip().upper(): i for i, v in enumerate(vals) if v is not None}
                        i_sku = hdr.get("SKU"); i_wh = hdr.get("WH")
                        i_oh  = hdr.get("STOCK_ON_HAND")
                        i_rs  = hdr.get("TSF_RESERVED_QTY")
                        i_ns  = hdr.get("NON_SELLABLE_QTY")
                        if None in (i_sku, i_wh, i_oh):
                            print("[stock_whs] cabeçalhos inesperados:", list(hdr)[:20])
                            return {}
                        continue
                    try:
                        sku = vals[i_sku]
                        if sku is None:
                            continue
                        sku = _norm_sku(sku)
                        wh  = _norm_sku(vals[i_wh]) if vals[i_wh] is not None else ""
                        oh  = float(vals[i_oh] or 0)
                        rs  = float(vals[i_rs] or 0) if i_rs is not None else 0.0
                        ns  = float(vals[i_ns] or 0) if i_ns is not None else 0.0
                        disp = oh - rs - ns
                        d = stocks.setdefault(sku, {})
                        d[wh] = d.get(wh, 0.0) + disp
                    except (IndexError, TypeError, ValueError):
                        continue
    except Exception as e:
        print(f"[stock_whs] erro a ler {src.name}: {e}")
        return {}
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"_mtime": src.stat().st_mtime, "_src": str(src),
                                     "stocks": stocks},
                                    ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return stocks
