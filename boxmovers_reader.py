"""
BoxMovers Excel Reader
======================
Lê BoxMovers2025_actual.xlsx e BoxMovers2026.xlsx directamente do SharePoint local.
Fornece dados reais (clientes, marcas, categorias, receita, margem) para o dashboard executivo.

Fallback gracioso: se os ficheiros não estiverem disponíveis (Railway/cloud), devolve {}.
"""

from __future__ import annotations

import warnings
from datetime import datetime
from pathlib import Path

# ── Índices de colunas (0-based) na sheet DEALS ────────────────────────────────
_C_DATE       = 0    # A  — DEAL DATE  (e.g. "Jan'26")
_C_STATUS     = 1    # B  — STATUS     (CONCLUÍDO / PO / ...)
_C_FATURACAO  = 2    # C  — FATURAÇÃO  (Faturado / ...)
_C_CLIENT     = 12   # M  — CLIENT
_C_CAT_CODE   = 16   # Q  — CAT code
_C_CAT_DESC   = 17   # R  — DESCRIÇÃO CAT
_C_BRAND      = 24   # Y  — BRAND
_C_SKU        = 25   # Z  — SKU
_C_TTL_SALES  = 43   # AR — TTL SALES (€)
_C_TTL_MG     = 59   # BH — TTL MG (€)
_C_MG_PCT     = 60   # BI — MG%4 (decimal, e.g. 0.053 = 5.3%)

# ── Índices de colunas na sheet "Deep Info 2.0" ───────────────────────────────
_DI_SKU       = 5    # F — SKU
_DI_CAT_CODE  = 1    # B — Categoria (code)
_DI_CAT_DESC  = 2    # C — Categoria Desc
_DI_BRAND     = 8    # I — MARCA

# Status que representam vendas concluídas / faturadas
_CONCLUDED = {"CONCLUÍDO", "CONCLUIDO"}

# Meses portugueses
_PT_MONTHS = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

# Marcas A-Brand conhecidas (para mix A-Brand %)
_ABRAND_KEYWORDS = {
    "SAMSUNG", "PHILIPS", "SONY", "LG", "BRAUN", "BABYLISS", "BOSCH",
    "SIEMENS", "TEFAL", "MOULINEX", "ROWENTA", "KRUPS", "DELONGHI", "DYSON",
    "SMEG", "BOSE", "CANON", "NIKON", "FUJIFILM", "PANASONIC", "TOSHIBA",
    "HISENSE", "TCL", "XIAOMI", "OPPO", "APPLE", "ASUS", "LENOVO", "HP",
    "GORENJE", "WHIRLPOOL", "SHARP", "NINTENDO", "REMINGTON", "DREAME",
    "COSORI", "AMAZON", "ELECTROLUX", "ZANUSSI", "AEG", "MIELE", "GRUNDIG",
    "HAIER", "CANDY", "HOOVER", "INDESIT", "HOTPOINT", "BEKO", "ARISTON",
    "PLAYSTATION", "PLAYSTAT", "SONY", "MICROSOFT", "XBOX",
}


# ── Resolução dos atalhos .lnk ─────────────────────────────────────────────────
def _resolve_lnk(lnk_path: Path) -> Path | None:
    try:
        import win32com.client
        sh  = win32com.client.Dispatch("WScript.Shell")
        lnk = sh.CreateShortcut(str(lnk_path))
        t   = Path(lnk.TargetPath)
        return t if t.exists() else None
    except Exception:
        return None


def _get_bm_paths() -> list[tuple[int, Path]]:
    """Devolve lista de (ano, Path) para os ficheiros BoxMovers disponíveis."""
    docs = Path(__file__).parent.parent / "Docs"
    candidates = [
        (2026, "BoxMovers2026.lnk"),
        (2025, "BoxMovers2025_actual - Atalho.lnk"),
    ]
    result = []
    for year, lnk_name in candidates:
        lnk = docs / lnk_name
        if lnk.exists():
            target = _resolve_lnk(lnk)
            if target:
                result.append((year, target))
    return result


# ── Deep Info index ─────────────────────────────────────────────────────────────
def _build_di_index(wb) -> dict:
    """
    Constrói SKU → {cat_desc, brand} a partir da sheet "Deep Info 2.0".
    Retorna {} se a sheet não existir.
    """
    ws = None
    for name in ("Deep Info 2.0", "Deep info"):
        if name in wb.sheetnames:
            ws = wb[name]
            break
    if ws is None:
        return {}

    index: dict = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for row in ws.iter_rows(min_row=2, values_only=True):
            sku = row[_DI_SKU]
            if sku is None:
                continue
            cat_desc = str(row[_DI_CAT_DESC] or "").strip()
            brand    = str(row[_DI_BRAND] or "").strip().upper()
            index[str(sku)] = {"cat_desc": cat_desc, "brand": brand}
    return index


# ── Parsing data ────────────────────────────────────────────────────────────────
def _parse_date(val) -> tuple[int | None, int | None]:
    """
    Converte "Jan'26", "Fev´26", datetime, etc. → (year, month).
    Suporta: apóstrofe simples (0x27), acento agudo (0xb4), aspas curvas (0x2018/0x2019).
    """
    if val is None:
        return None, None
    if isinstance(val, datetime):
        return val.year, val.month
    s = str(val).strip().lower()
    # Normalizar todos os separadores possíveis → apóstrofe simples
    for ch in ("\u00b4", "\u2019", "\u2018", "\u0060", "\u02bc"):
        s = s.replace(ch, "'")
    if "'" in s:
        parts = s.split("'")
        m_str = parts[0].strip()[:3]
        y_str = parts[1].strip()[:4]
        m = _PT_MONTHS.get(m_str)
        try:
            y = int(y_str)
            if y < 100:
                y += 2000
            return y, m
        except ValueError:
            pass
    return None, None


# ── Leitura principal ───────────────────────────────────────────────────────────
def read_bm_deals(year_filter: int | None = None) -> list[dict]:
    """
    Lê todas as linhas com SKU dos ficheiros BoxMovers.
    Preenche campos vazios (marca, categoria) via Deep Info.
    Retorna lista de dicts com chaves normalizadas.
    """
    try:
        import openpyxl
    except ImportError:
        return []

    paths = _get_bm_paths()
    if not paths:
        return []

    all_rows: list[dict] = []

    for bm_year, path in paths:
        if year_filter and bm_year != year_filter:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)

            di = _build_di_index(wb)
            ws = wb["DEALS"]

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                for row in ws.iter_rows(min_row=3, values_only=True):
                    sku = row[_C_SKU]
                    if sku is None:
                        continue

                    sku_str  = str(sku)
                    status   = str(row[_C_STATUS] or "").strip()
                    client   = str(row[_C_CLIENT] or "").strip()
                    brand    = str(row[_C_BRAND]  or "").strip().upper()
                    cat      = str(row[_C_CAT_DESC] or "").strip()
                    revenue  = float(row[_C_TTL_SALES] or 0)
                    mg_eur   = float(row[_C_TTL_MG]    or 0)
                    mg_pct   = float(row[_C_MG_PCT]    or 0) * 100  # 0.053 → 5.3

                    yr, mo = _parse_date(row[_C_DATE])
                    if yr is None:
                        yr = bm_year

                    # Enriquecimento via Deep Info quando campos vazios
                    di_entry = di.get(sku_str, {})
                    if not brand and di_entry.get("brand"):
                        brand = di_entry["brand"]
                    if not cat and di_entry.get("cat_desc"):
                        cat = di_entry["cat_desc"]

                    all_rows.append({
                        "client":     client   or "—",
                        "brand":      brand    or "—",
                        "cat":        cat      or "—",
                        "sku":        sku_str,
                        "revenue":    revenue,
                        "mg_eur":     mg_eur,
                        "mg_pct":     round(mg_pct, 2),
                        "year":       yr,
                        "month":      mo or 1,
                        "status":     status,
                        "bm_year":    bm_year,
                        "concluded":  status.upper().replace("Í", "I") in {s.replace("Í", "I") for s in _CONCLUDED},
                    })

            wb.close()

        except Exception as e:
            print(f"[boxmovers_reader] Erro ao ler {path}: {e}")

    return all_rows


# ── Dados agregados para o dashboard ───────────────────────────────────────────
def get_bm_dashboard_data(year: int | None = None) -> dict:
    """
    Devolve dict com métricas agregadas para o dashboard executivo.
    Retorna {} se os ficheiros não estiverem disponíveis.

    Filtra por ano se `year` for passado.
    Usa apenas deals CONCLUÍDO para receita/margem reais.
    """
    rows = read_bm_deals(year_filter=year)
    if not rows:
        return {}

    # ── Filtragem por ano (quando não foi filtrado na leitura) ─────────────────
    if year:
        rows = [r for r in rows if r["year"] == year]
    if not rows:
        return {}

    concluded = [r for r in rows if r["concluded"]]

    # ── Receita e margem totais (apenas concluídos) ────────────────────────────
    total_rev   = sum(r["revenue"] for r in concluded)
    total_mg    = sum(r["mg_eur"]  for r in concluded)
    avg_mg_pct  = round(total_mg / total_rev * 100, 2) if total_rev else 0.0

    # ── Top cliente ────────────────────────────────────────────────────────────
    client_rev: dict[str, float] = {}
    for r in concluded:
        c = r["client"]
        client_rev[c] = client_rev.get(c, 0) + r["revenue"]
    top_client     = max(client_rev, key=client_rev.get) if client_rev else "—"
    top_client_rev = round(client_rev.get(top_client, 0), 0)

    # ── Top marca e mix A-Brand ─────────────────────────────────────────────────
    brand_rev: dict[str, float] = {}
    abrand_total = 0.0
    for r in concluded:
        b = r["brand"]
        if b and b != "—":
            brand_rev[b] = brand_rev.get(b, 0) + r["revenue"]
            # A-Brand: marca conhecida
            if any(kw in b.upper() for kw in _ABRAND_KEYWORDS):
                abrand_total += r["revenue"]
    top_brand  = max(brand_rev, key=brand_rev.get) if brand_rev else "—"
    mix_abrand = round(abrand_total / total_rev * 100, 0) if total_rev else 0.0

    # ── Ticket médio (por deal — agrupa por cliente+mês) ──────────────────────
    deal_keys: set = set()
    for r in concluded:
        deal_keys.add((r["client"], r["year"], r["month"]))
    avg_ticket = round(total_rev / len(deal_keys), 0) if deal_keys else 0.0

    # ── Receita mensal ─────────────────────────────────────────────────────────
    monthly_rev:    dict[str, float] = {}
    monthly_mg:     dict[str, float] = {}
    monthly_mg_pct: dict[str, float] = {}

    for r in concluded:
        key = f"{r['year']}-{r['month']:02d}"
        monthly_rev[key] = monthly_rev.get(key, 0) + r["revenue"]
        monthly_mg[key]  = monthly_mg.get(key, 0)  + r["mg_eur"]

    for k in monthly_rev:
        rev_k = monthly_rev[k]
        mg_k  = monthly_mg.get(k, 0)
        monthly_mg_pct[k] = round(mg_k / rev_k * 100, 2) if rev_k > 0 else 0.0

    monthly_sorted     = dict(sorted(monthly_rev.items()))
    monthly_mg_sorted  = dict(sorted(monthly_mg.items()))
    monthly_mgp_sorted = dict(sorted(monthly_mg_pct.items()))

    # ── Proveito (BoxMovers fee: margem × taxa comissão) ───────────────────────
    try:
        from config import bp_commission_rate, bp_commission_tier_name
        commission_rate = bp_commission_rate(total_rev)
        tier_name       = bp_commission_tier_name(total_rev)
    except Exception:
        commission_rate = 0.175
        tier_name       = "Base"
    our_cut = round(total_mg * commission_rate, 0)

    monthly_proveito = {
        k: round(monthly_mg.get(k, 0) * commission_rate, 2)
        for k in monthly_sorted
    }

    # ── Distribuição por categoria ─────────────────────────────────────────────
    cat_rev: dict[str, float] = {}
    for r in concluded:
        c = r["cat"]
        cat_rev[c] = cat_rev.get(c, 0) + r["revenue"]

    return {
        # KPIs
        "total_revenue":      round(total_rev, 2),
        "gross_margin_value": round(total_mg, 2),
        "avg_margin":         avg_mg_pct,
        "our_cut":            our_cut,
        "commission_rate_pct": round(commission_rate * 100, 1),
        "tier_name":          tier_name,
        # Drivers
        "top_client":         top_client,
        "top_client_rev":     top_client_rev,
        "top_brand":          top_brand,
        "mix_abrand":         mix_abrand,
        "avg_ticket":         avg_ticket,
        # Mensais
        "monthly_revenue":    monthly_sorted,
        "monthly_margin":     monthly_mg_sorted,
        "monthly_margin_pct": monthly_mgp_sorted,
        "monthly_proveito":   monthly_proveito,
        # Extras
        "by_client":          dict(sorted(client_rev.items(), key=lambda x: x[1], reverse=True)),
        "by_brand":           dict(sorted(brand_rev.items(),  key=lambda x: x[1], reverse=True)),
        "by_cat":             dict(sorted(cat_rev.items(),    key=lambda x: x[1], reverse=True)),
        # Contagens
        "n_concluded":        len(concluded),
        "n_all":              len(rows),
        "source":             "boxmovers",
    }
