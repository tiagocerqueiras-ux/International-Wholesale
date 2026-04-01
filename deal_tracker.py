"""
Deal Tracker — Supabase
=======================
Regista cotações, atualiza status e lista deals em curso.
API idêntica à versão Excel para compatibilidade com app.py.
"""

import json
from datetime import datetime

from config import SUPABASE_URL, SUPABASE_KEY, STATUSES

# ── SQL para executar no Supabase (uma única vez) ─────────────────────────────
# ALTER TABLE deals
#   ADD COLUMN IF NOT EXISTS order_date        TEXT,
#   ADD COLUMN IF NOT EXISTS expected_delivery TEXT,
#   ADD COLUMN IF NOT EXISTS actual_delivery   TEXT,
#   ADD COLUMN IF NOT EXISTS invoice_number    TEXT,
#   ADD COLUMN IF NOT EXISTS invoice_date      TEXT,
#   ADD COLUMN IF NOT EXISTS invoice_value     NUMERIC,
#   ADD COLUMN IF NOT EXISTS cmr_number        TEXT,
#   ADD COLUMN IF NOT EXISTS packing_list      TEXT,
#   ADD COLUMN IF NOT EXISTS supplier_ids      TEXT;
# ─────────────────────────────────────────────────────────────────────────────

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
    "order_date":         "Data Encomenda",
    "expected_delivery":  "Entrega Prevista",
    "actual_delivery":    "Entrega Real",
    "invoice_number":     "Nº Fatura",
    "invoice_date":       "Data Fatura",
    "invoice_value":      "Valor Fatura (€)",
    "cmr_number":         "CMR Nº",
    "packing_list":       "Packing List Nº",
    "supplier_ids":       "Fornecedor(es)",
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


def update_deal_operational(
    deal_id: str,
    order_date: str = None,
    expected_delivery: str = None,
    actual_delivery: str = None,
    invoice_number: str = None,
    invoice_date: str = None,
    invoice_value: float = None,
    cmr_number: str = None,
    packing_list: str = None,
    supplier_ids: str = None,
) -> bool:
    """Atualiza campos operacionais/logísticos de um deal."""
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        upd: dict = {"updated_at": now}
        if order_date        is not None: upd["order_date"]         = order_date
        if expected_delivery is not None: upd["expected_delivery"]  = expected_delivery
        if actual_delivery   is not None: upd["actual_delivery"]    = actual_delivery
        if invoice_number    is not None: upd["invoice_number"]     = invoice_number
        if invoice_date      is not None: upd["invoice_date"]       = invoice_date
        if invoice_value     is not None: upd["invoice_value"]      = round(float(invoice_value), 2)
        if cmr_number        is not None: upd["cmr_number"]         = cmr_number
        if packing_list      is not None: upd["packing_list"]       = packing_list
        if supplier_ids      is not None: upd["supplier_ids"]       = supplier_ids
        _get_client().table("deals").update(upd).eq("deal_id", deal_id).execute()
        return True
    except Exception as e:
        print(f"[deal_tracker] update_deal_operational erro: {e}")
        return False


def get_pipeline_stats(salesperson_filter: str = None) -> dict:
    """
    Retorna estatísticas do pipeline agrupadas por status.
    Devolve dict: {status: {"count": int, "value": float}}
    e também lista de deals "em risco" (sem update há > DEAL_STALE_DAYS dias).
    """
    from config import DEAL_STALE_DAYS
    try:
        q = _get_client().table("deals").select(
            "deal_id,client,status,proposed_value,updated_at,salesperson_email"
        )
        if salesperson_filter:
            q = q.ilike("salesperson_email", salesperson_filter)
        res = q.execute()
        rows = res.data or []

        stats: dict = {}
        stale: list = []
        now = datetime.now()

        for r in rows:
            st_   = r.get("status") or "Rascunho"
            val   = float(r.get("proposed_value") or 0)
            if st_ not in stats:
                stats[st_] = {"count": 0, "value": 0.0}
            stats[st_]["count"] += 1
            stats[st_]["value"] += val

            # Risk check — deals in non-closed statuses
            from config import PIPELINE_CLOSED_STATUSES
            if st_ not in PIPELINE_CLOSED_STATUSES:
                upd_str = (r.get("updated_at") or "")[:16]
                try:
                    upd_dt = datetime.strptime(upd_str, "%Y-%m-%d %H:%M")
                    diff   = (now - upd_dt).days
                    if diff >= DEAL_STALE_DAYS:
                        stale.append({
                            "deal_id": r.get("deal_id"),
                            "client":  r.get("client"),
                            "status":  st_,
                            "days":    diff,
                            "value":   val,
                        })
                except Exception:
                    pass

        # Round values
        for st_ in stats:
            stats[st_]["value"] = round(stats[st_]["value"], 2)

        return {"by_status": stats, "stale": stale}
    except Exception as e:
        print(f"[deal_tracker] get_pipeline_stats erro: {e}")
        return {"by_status": {}, "stale": []}


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


def duplicate_deal(
    deal_id: str,
    new_client: str,
    new_email: str,
    new_country: str = "",
    new_company: str = "",
) -> str:
    """Duplica um deal existente para um novo cliente. Devolve o novo deal_id."""
    try:
        client = _get_client()
        res = client.table("deals").select("*").eq("deal_id", deal_id).single().execute()
        if not res.data:
            return ""
        row = dict(res.data)
        new_id  = _next_deal_id()
        now     = datetime.now().strftime("%Y-%m-%d %H:%M")
        row["deal_id"]      = new_id
        row["client"]       = new_client          # nome do contacto (pessoa)
        row["client_email"] = new_email
        row["country"]      = new_country or row.get("country", "")
        row["company"]      = new_company if new_company else row.get("company", "")
        row["status"]       = "Rascunho"
        row["created_at"]   = now
        row["updated_at"]   = now
        row["notes"]        = f"Duplicado de {deal_id}"
        row.pop("id", None)   # remover PK auto
        client.table("deals").insert(row).execute()
        return new_id
    except Exception as e:
        print(f"[deal_tracker] duplicate_deal erro: {e}")
        return ""


def delete_deal(deal_id: str) -> bool:
    """Apaga permanentemente um deal."""
    try:
        _get_client().table("deals").delete().eq("deal_id", deal_id).execute()
        return True
    except Exception as e:
        print(f"[deal_tracker] delete_deal erro: {e}")
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


def get_sku_price_history(sku_id: str, limit: int = 8) -> list:
    """
    Devolve o histórico de deals que contêm o SKU indicado.
    Útil para o Pricing Engine mostrar preços negociados anteriormente.
    Devolve lista de dicts com: deal_id, client, country, date, status,
    margin_pct, proposed_value, language — ordenados por data desc.
    """
    try:
        res = (_get_client().table("deals")
               .select("deal_id,client,company,country,created_at,status,"
                       "margin_pct,proposed_value,language,sku_ids")
               .ilike("sku_ids", f"%{sku_id}%")
               .order("created_at", desc=True)
               .limit(limit)
               .execute())
        return res.data or []
    except Exception as e:
        print(f"[deal_tracker] get_sku_price_history erro: {e}")
        return []


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


def get_executive_dashboard_data(year: int = None, salesperson_filter: str = None) -> dict:
    """
    Agrega dados para o Dashboard Executivo.
    Devolve: revenue, pipeline, margin, P&L estimado, por comercial, por mês.
    """
    from config import PIPELINE_CLOSED_STATUSES, PIPELINE_ACTIVE_STATUSES, BP_OUR_CUT_PCT

    def _parse_margin(val) -> float:
        try:
            return float(str(val or "0").replace("%", "").strip())
        except Exception:
            return 0.0

    try:
        q = _get_client().table("deals").select(
            "deal_id,client,country,status,proposed_value,invoice_value,"
            "margin_pct,salesperson_email,created_at,updated_at"
        )
        if salesperson_filter:
            q = q.ilike("salesperson_email", salesperson_filter)
        res = q.execute()
        rows = res.data or []
    except Exception as e:
        print(f"[deal_tracker] get_executive_dashboard_data erro: {e}")
        return {}

    # Filter by year if requested
    if year:
        rows = [r for r in rows if str(r.get("created_at","")).startswith(str(year))]

    # ── Categorize ────────────────────────────────────────────────────────
    # "Faturado" é o status final de ganho no pipeline actual (13 statuses).
    # "Fechado" era usado em versões anteriores — manter por retrocompatibilidade
    # com dados históricos, mas o status corrente é "Faturado".
    faturado_statuses = {"Faturado"}
    closed_win        = {"Faturado"}          # removido "Fechado" — não existe no pipeline actual
    closed_lost       = {"Perdido"}
    active_statuses   = set(PIPELINE_ACTIVE_STATUSES)
    order_statuses    = {"Encomenda Confirmada", "Em Preparação", "Expedido", "Entregue"}
    # "Arquivado" pertence a PIPELINE_CLOSED_STATUSES — não conta como revenue

    revenue_rows  = [r for r in rows if r.get("status") in closed_win | faturado_statuses | order_statuses]
    pipeline_rows = [r for r in rows if r.get("status") in active_statuses]
    won_rows      = [r for r in rows if r.get("status") in closed_win]
    lost_rows     = [r for r in rows if r.get("status") in closed_lost]

    def _val(r):
        v = r.get("invoice_value") or r.get("proposed_value") or 0
        try: return float(v)
        except: return 0.0

    total_revenue  = round(sum(_val(r) for r in revenue_rows), 2)
    total_pipeline = round(sum(_val(r) for r in pipeline_rows), 2)

    # Weighted average margin (for deals with a value)
    _margin_total = sum(_val(r) * _parse_margin(r.get("margin_pct")) for r in revenue_rows if _val(r) > 0)
    _margin_base  = sum(_val(r) for r in revenue_rows if _val(r) > 0)
    avg_margin    = round(_margin_total / _margin_base, 2) if _margin_base else 0.0

    gross_margin_value = round(total_revenue * avg_margin / 100, 2)
    our_cut            = round(gross_margin_value * BP_OUR_CUT_PCT, 2)

    # Win rate
    total_closed = len(won_rows) + len(lost_rows)
    win_rate     = round(len(won_rows) / total_closed * 100, 1) if total_closed else 0.0

    # ── Per salesperson ───────────────────────────────────────────────────
    sp_data: dict = {}
    for r in rows:
        sp = (r.get("salesperson_email") or "sem_email").lower().strip()
        if sp not in sp_data:
            sp_data[sp] = {
                "email":    sp,
                "revenue":  0.0,
                "pipeline": 0.0,
                "won":      0,
                "lost":     0,
                "active":   0,
                "margin_w": 0.0,
                "margin_b": 0.0,
            }
        v = _val(r)
        st_ = r.get("status","")
        if st_ in closed_win | faturado_statuses | order_statuses:
            sp_data[sp]["revenue"]  += v
            sp_data[sp]["margin_w"] += v * _parse_margin(r.get("margin_pct"))
            sp_data[sp]["margin_b"] += v
        if st_ in active_statuses:
            sp_data[sp]["pipeline"] += v
            sp_data[sp]["active"]   += 1
        if st_ in closed_win:
            sp_data[sp]["won"]  += 1
        if st_ in closed_lost:
            sp_data[sp]["lost"] += 1

    sp_list = []
    for sp, d in sp_data.items():
        avg_m = round(d["margin_w"] / d["margin_b"], 2) if d["margin_b"] else 0.0
        sp_list.append({
            "email":      d["email"],
            "revenue":    round(d["revenue"], 2),
            "pipeline":   round(d["pipeline"], 2),
            "won":        d["won"],
            "lost":       d["lost"],
            "active":     d["active"],
            "avg_margin": avg_m,
            "win_rate":   round(d["won"] / (d["won"] + d["lost"]) * 100, 1)
                          if (d["won"] + d["lost"]) > 0 else 0.0,
        })
    sp_list.sort(key=lambda x: -x["revenue"])

    # ── Monthly revenue + margin + proveito ──────────────────────────────
    monthly:          dict = {}
    monthly_margin:   dict = {}
    monthly_proveito: dict = {}
    for r in revenue_rows:
        dt_str = str(r.get("created_at",""))[:7]  # "YYYY-MM"
        if dt_str and len(dt_str) == 7:
            v      = _val(r)
            mg_pct = _parse_margin(r.get("margin_pct"))   # e.g. 5.3 (percent)
            mg_val = round(v * mg_pct / 100, 2)           # margem bruta €
            prov   = round(mg_val * BP_OUR_CUT_PCT, 2)    # proveito BoxMovers €
            monthly[dt_str]          = round(monthly.get(dt_str, 0.0)          + v,      2)
            monthly_margin[dt_str]   = round(monthly_margin.get(dt_str, 0.0)   + mg_val, 2)
            monthly_proveito[dt_str] = round(monthly_proveito.get(dt_str, 0.0) + prov,   2)
    monthly_sorted          = dict(sorted(monthly.items()))
    monthly_margin_sorted   = dict(sorted(monthly_margin.items()))
    monthly_proveito_sorted = dict(sorted(monthly_proveito.items()))

    # ── Deals by status count ─────────────────────────────────────────────
    status_counts: dict = {}
    for r in rows:
        st_ = r.get("status","—")
        status_counts[st_] = status_counts.get(st_, 0) + 1

    return {
        "total_revenue":       total_revenue,
        "total_pipeline":      total_pipeline,
        "avg_margin":          avg_margin,
        "gross_margin_value":  gross_margin_value,
        "our_cut":             our_cut,
        "win_rate":            win_rate,
        "total_deals":         len(rows),
        "won_deals":           len(won_rows),
        "lost_deals":          len(lost_rows),
        "by_salesperson":      sp_list,
        "monthly_revenue":     monthly_sorted,
        "monthly_margin":      monthly_margin_sorted,
        "monthly_proveito":    monthly_proveito_sorted,
        "status_counts":       status_counts,
    }
