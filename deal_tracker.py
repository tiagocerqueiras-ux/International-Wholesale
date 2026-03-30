"""
Deal Tracker — Supabase
=======================
Regista cotações, atualiza status e lista deals em curso.
API idêntica à versão Excel para compatibilidade com app.py.
"""

import json
from datetime import datetime

from config import SUPABASE_URL, SUPABASE_KEY, STATUSES

# ── Cliente Supabase ───────────────────────────────────────────────────────────

def _get_client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Geração de Deal ID ─────────────────────────────────────────────────────────

def _next_deal_id() -> str:
    year   = datetime.now().year
    prefix = f"BM-{year}-"
    try:
        client = _get_client()
        res = (
            client.table("deals")
            .select("deal_id")
            .like("deal_id", f"{prefix}%")
            .order("deal_id", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            last = res.data[0]["deal_id"]
            num  = int(last[len(prefix):]) + 1
        else:
            num = 1
    except Exception:
        num = 1
    # Garantir unicidade — avançar até encontrar ID livre
    client = _get_client()
    while True:
        candidate = f"{prefix}{num:03d}"
        check = client.table("deals").select("deal_id").eq("deal_id", candidate).execute()
        if not check.data:
            return candidate
        num += 1


# ── Mapeamento HEADERS → chaves internas (para list_deals / get_deal) ─────────

HEADERS = [
    "Deal ID", "Data Criação", "Cliente", "País", "Email Cliente",
    "Língua", "SKUs", "Produtos", "UFC Médio (€)", "EIS Dir. Autor (€)",
    "Apoio Sell-In", "Apoio Sell-Out", "Qty Total", "Valor Proposto (€)",
    "Margem %", "Incoterm", "Pagamento", "IVA", "Frete (€)",
    "Availability / ETA", "Status", "Data Último Update", "Notas",
]

_DB_TO_HEADER = {
    "deal_id":            "Deal ID",
    "created_at":         "Data Criação",
    "client":             "Cliente",
    "country":            "País",
    "client_email":       "Email Cliente",
    "language":           "Língua",
    "sku_ids":            "SKUs",
    "products":           "Produtos",
    "avg_unit_cost":      "UFC Médio (€)",
    "eis_da_total":       "EIS Dir. Autor (€)",
    "has_sell_in":        "Apoio Sell-In",
    "has_sell_out":       "Apoio Sell-Out",
    "qty_total":          "Qty Total",
    "proposed_value":     "Valor Proposto (€)",
    "margin_pct":         "Margem %",
    "incoterm":           "Incoterm",
    "payment_conditions": "Pagamento",
    "vat":                "IVA",
    "freight":            "Frete (€)",
    "availability":       "Availability / ETA",
    "status":             "Status",
    "updated_at":         "Data Último Update",
    "notes":              "Notas",
}


def _row_to_deal(row: dict) -> dict:
    """Converte linha Supabase → dict com chaves HEADERS (compatível com app.py)."""
    d = {_DB_TO_HEADER.get(k, k): v for k, v in row.items()}
    # skus_detail já vem como dict/JSONB — preservar
    if "skus_detail" in row:
        d["_skus_detail"] = row["skus_detail"] or {}
    return d


# ── CRUD ───────────────────────────────────────────────────────────────────────

def add_deal(
    client: str,
    country: str,
    email: str,
    language: str,
    skus_data: dict,
    notes: str = "",
    margin_pct: float = None,
    pvp_total: float = None,
    vat_rate: float = 0.0,
    incoterm: str = "",
    payment_conditions: str = "",
    freight_cost: float = 0.0,
    availability: str = "",
    salesperson_email: str = "",
    company: str = "",
) -> str:
    deal_id = _next_deal_id()
    now     = datetime.now().strftime("%Y-%m-%d %H:%M")

    sku_ids = []
    products = []
    total_cost_weighted = 0.0
    total_qty   = 0
    total_eis   = 0.0
    has_sell_in = False
    has_sell_out = False

    for sku, info in skus_data.items():
        d   = info.get("data") or {}
        qty = int(info.get("qty") or 1)
        uc  = info.get("fc_final") or d.get("ufc_raw") or 0.0
        sku_ids.append(sku)
        products.append(f"{d.get('name', sku)[:60]} (x{qty})")
        total_cost_weighted += uc * qty
        total_eis += (d.get("eis_da") or 0.0) * qty
        total_qty += qty
        if d.get("sell_in")  is not None: has_sell_in  = True
        if d.get("sell_out") is not None: has_sell_out = True

    avg_uc    = round(total_cost_weighted / total_qty, 4) if total_qty else 0.0
    vat_label = f"IVA {int(vat_rate*100)}%" if vat_rate > 0 else "Isento"

    row = {
        "deal_id":            deal_id,
        "created_at":         now,
        "client":             client,
        "country":            country,
        "client_email":       email,
        "language":           language.upper(),
        "sku_ids":            ", ".join(sku_ids),
        "products":           "; ".join(products),
        "avg_unit_cost":      avg_uc,
        "eis_da_total":       round(total_eis, 2),
        "has_sell_in":        "Sim" if has_sell_in  else "Não",
        "has_sell_out":       "Sim" if has_sell_out else "Não",
        "qty_total":          total_qty,
        "proposed_value":     round(pvp_total, 2) if pvp_total else None,
        "margin_pct":         f"{margin_pct:.1f}%" if margin_pct is not None else None,
        "incoterm":           incoterm,
        "payment_conditions": payment_conditions,
        "vat":                vat_label,
        "freight":            round(freight_cost, 2),
        "availability":       availability,
        "status":             "Rascunho",
        "updated_at":         now,
        "notes":              notes,
        "skus_detail":        skus_data,
        "salesperson_email":  salesperson_email,
        "company":            company,
    }

    _get_client().table("deals").insert(row).execute()
    return deal_id


def update_status(deal_id: str, new_status: str, notes: str = "") -> bool:
    if new_status not in STATUSES:
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        client = _get_client()
        # Buscar notas actuais
        existing_notes = ""
        if notes:
            res = client.table("deals").select("notes").eq("deal_id", deal_id).single().execute()
            existing_notes = (res.data or {}).get("notes", "") or ""
            stamp = datetime.now().strftime("%d/%m %H:%M")
            sep   = "\n" if existing_notes else ""
            notes = f"{existing_notes}{sep}[{stamp}] {notes}"

        upd = {"status": new_status, "updated_at": now}
        if notes:
            upd["notes"] = notes
        client.table("deals").update(upd).eq("deal_id", deal_id).execute()
        return True
    except Exception as e:
        print(f"[deal_tracker] update_status erro: {e}")
        return False


def update_margin(deal_id: str, margin_pct: float, pvp_total: float = None) -> bool:
    try:
        upd = {
            "margin_pct": f"{margin_pct:.1f}%",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        if pvp_total is not None:
            upd["proposed_value"] = round(pvp_total, 2)
        _get_client().table("deals").update(upd).eq("deal_id", deal_id).execute()
        return True
    except Exception as e:
        print(f"[deal_tracker] update_margin erro: {e}")
        return False


def update_deal_prices(deal_id: str, skus_data: dict, pvp_total: float, margin_pct: float) -> bool:
    """Atualiza skus_detail, valor proposto e margem de um deal existente."""
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Recalcular produtos e qtd total
        products = []
        qty_total = 0
        for sku, info in skus_data.items():
            d   = info.get("data") or {}
            qty = int(info.get("qty") or 1)
            products.append(f"{d.get('name', sku)[:60]} (x{qty})")
            qty_total += qty
        _get_client().table("deals").update({
            "skus_detail":    skus_data,
            "proposed_value": round(pvp_total, 2),
            "margin_pct":     f"{margin_pct:.1f}%",
            "qty_total":      qty_total,
            "products":       "; ".join(products),
            "updated_at":     now,
        }).eq("deal_id", deal_id).execute()
        return True
    except Exception as e:
        print(f"[deal_tracker] update_deal_prices erro: {e}")
        return False


def list_deals(status_filter: str = None, salesperson_filter: str = None) -> list:
    try:
        q = _get_client().table("deals").select(
            "deal_id,created_at,client,country,client_email,language,"
            "sku_ids,products,avg_unit_cost,eis_da_total,has_sell_in,has_sell_out,"
            "qty_total,proposed_value,margin_pct,incoterm,payment_conditions,"
            "vat,freight,availability,status,updated_at,notes,salesperson_email"
        ).order("created_at", desc=False)
        if status_filter:
            q = q.eq("status", status_filter)
        if salesperson_filter:
            q = q.ilike("salesperson_email", salesperson_filter)
        res = q.execute()
        return [_row_to_deal(r) for r in (res.data or [])]
    except Exception as e:
        print(f"[deal_tracker] list_deals erro: {e}")
        return []


def get_deal(deal_id: str) -> dict | None:
    try:
        res = (
            _get_client()
            .table("deals")
            .select("*")
            .eq("deal_id", deal_id)
            .single()
            .execute()
        )
        if res.data:
            return _row_to_deal(res.data)
        return None
    except Exception as e:
        print(f"[deal_tracker] get_deal erro: {e}")
        return None


def deal_products_table(deal: dict) -> list[dict]:
    """Converte _skus_detail em lista de dicts com as mesmas colunas da cotação."""
    rows = []
    skus = deal.get("_skus_detail") or {}
    for sku, info in skus.items():
        d      = info.get("data") or {}
        qty    = int(info.get("qty") or 1)
        so_neg = float(info.get("so_neg") or 0)
        fc_fin = float(info.get("fc_final") or 0)
        pvp    = float(info.get("pvp") or 0)
        rows.append({
            "SKU":              sku,
            "EAN":              str(d.get("ean") or ""),
            "Produto":          str(d.get("name") or ""),
            "Marca":            str(d.get("brand") or ""),
            "PVP PT (€)":       round(float(d.get("pvp_pt") or 0), 2),
            "UFC (€)":          round(float(d.get("ufc_raw") or 0), 2),
            "EIS DA (€)":       round(float(d.get("eis_da") or 0), 2),
            "Sell-Out Sim (€)": round(float(d.get("sell_out") or 0), 2),
            "SO Neg (€)":       round(so_neg, 2),
            "FC Final (€)":     round(fc_fin, 2),
            "PVP Proposto (€)": round(pvp, 2),
            "Qty":              qty,
            "Total (€)":        round(pvp * qty, 2),
        })
    return rows
