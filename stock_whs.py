"""
stock_whs.py — Stocks diários por armazém (Pendentes África.xlsb, tab STK WHs)
==============================================================================
O simulador African Markets tem stocks desatualizados; a fonte diária correta é
o ficheiro SharePoint "Pendentes África.xlsb" (site STOCK & SPACE MANAGEMENT),
sincronizado via OneDrive. Este módulo lê a tab STK WHs e devolve, por SKU e
armazém: disponível = STOCK_ON_HAND − TSF_RESERVED_QTY − NON_SELLABLE_QTY.

Cache em .cache/stock_whs.json com gate por mtime (o xlsb tem ~76MB; a leitura
demora ~1-2 min e só é refeita quando o ficheiro muda).
"""
import json
from pathlib import Path

_CANDIDATES = [
    Path.home() / "OneDrive - Worten" / "STOCK & SPACE MANAGEMENT - África" / "Pendentes África.xlsb",
    Path.home() / "Worten" / "STOCK & SPACE MANAGEMENT - África" / "Pendentes África.xlsb",
]
CACHE = Path(__file__).resolve().parent / ".cache" / "stock_whs.json"
SHEET = "STK WHs"


def find_file():
    for c in _CANDIDATES:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return None


def _norm_sku(v) -> str:
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def build(force: bool = False) -> dict:
    """{sku: {"701": disp, "708": disp, "2928": disp, ...}} — vazio se indisponível."""
    src = find_file()
    if src is None:
        return {}
    # cache válida?
    if CACHE.exists() and not force:
        try:
            payload = json.loads(CACHE.read_text(encoding="utf-8"))
            if payload.get("_mtime") == src.stat().st_mtime:
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
        CACHE.write_text(json.dumps({"_mtime": src.stat().st_mtime, "stocks": stocks},
                                    ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return stocks
