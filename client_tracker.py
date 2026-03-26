"""
Client Tracker — Supabase CRM
==============================
Gestão centralizada de clientes B2B para BoxMovers Export.
"""

from datetime import datetime
from config import SUPABASE_URL, SUPABASE_KEY

CLIENT_STATUSES = ["Ativo", "Inativo", "Prospeto", "Bloqueado"]
CLIENT_TYPES    = ["Distribuidor", "Retalhista", "Marketplace", "Agente", "Outro"]
MARKETS         = ["EU", "África", "Médio Oriente", "Outros"]

BRANDS_LIST = [
    "BABYLISS","BOSCH","BRAUN","CANON","FUJIFILM","FUJI INSTAX",
    "BOSE","GARMIN","MOULINEX","KRUPS","HISENSE","PHILIPS","SMEG",
    "PLAYSTATION","REMINGTON","RUSSELL HOBBS","APPLE","OPPO",
    "GOOGLE PIXEL","COSORI","ROWENTA","TEFAL","DYSON","DE'LONGHI",
    "NESPRESSO","SAMSUNG","LG","SONY","XIAOMI","OUTRAS",
]

CATEGORIES_LIST = ["SPH","AUDIO","MDA","SDA","TV","IT","FOTO","GAM","VC","OTH"]


def _get_client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── CRUD ───────────────────────────────────────────────────────────────────────

def add_client(data: dict) -> str:
    """Cria cliente. Devolve o id gerado."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    row = {
        "company_name":        data.get("company_name", ""),
        "legal_name":          data.get("legal_name", ""),
        "vat":                 data.get("vat", ""),
        "country":             data.get("country", ""),
        "market":              data.get("market", "EU"),
        "region":              data.get("region", ""),
        "address":             data.get("address", ""),
        "zip_code":            data.get("zip_code", ""),
        "city":                data.get("city", ""),
        "contact_name":        data.get("contact_name", ""),
        "contact_role":        data.get("contact_role", ""),
        "contact_email":       data.get("contact_email", ""),
        "contact_phone":       data.get("contact_phone", ""),
        "contact_linkedin":    data.get("contact_linkedin", ""),
        "client_type":         data.get("client_type", "Distribuidor"),
        "status":              data.get("status", "Ativo"),
        "brands":              data.get("brands", []),
        "categories":          data.get("categories", []),
        "incoterm":            data.get("incoterm", ""),
        "currency":            data.get("currency", "EUR"),
        "payment_method":      data.get("payment_method", ""),
        "payment_terms":       data.get("payment_terms", ""),
        "notes":               data.get("notes", ""),
        "created_at":          now,
        "updated_at":          now,
    }
    res = _get_client().table("clients").insert(row).execute()
    return str(res.data[0]["id"]) if res.data else ""


def update_client(client_id: str, data: dict) -> bool:
    try:
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _get_client().table("clients").update(data).eq("id", client_id).execute()
        return True
    except Exception as e:
        print(f"[client_tracker] update_client erro: {e}")
        return False


def get_client(client_id: str) -> dict | None:
    try:
        res = _get_client().table("clients").select("*").eq("id", client_id).single().execute()
        return res.data or None
    except Exception as e:
        print(f"[client_tracker] get_client erro: {e}")
        return None


def get_client_by_email(email: str) -> dict | None:
    try:
        res = (_get_client().table("clients")
               .select("*").ilike("contact_email", email).limit(1).execute())
        return res.data[0] if res.data else None
    except Exception:
        return None


def list_clients(
    status: str = None,
    market: str = None,
    country: str = None,
    client_type: str = None,
    search: str = None,
) -> list:
    try:
        q = _get_client().table("clients").select(
            "id,company_name,country,market,contact_email,contact_phone,"
            "client_type,status,brands,categories,incoterm,payment_terms,"
            "notes,created_at,updated_at"
        ).order("company_name")
        if status:      q = q.eq("status", status)
        if market:      q = q.eq("market", market)
        if country:     q = q.ilike("country", f"%{country}%")
        if client_type: q = q.eq("client_type", client_type)
        if search:      q = q.ilike("company_name", f"%{search}%")
        res = q.execute()
        return res.data or []
    except Exception as e:
        print(f"[client_tracker] list_clients erro: {e}")
        return []


def count_clients() -> int:
    try:
        res = _get_client().table("clients").select("id", count="exact").execute()
        return res.count or 0
    except Exception:
        return 0


def get_client_deals(client_email: str) -> list:
    """Devolve todos os deals de um cliente pelo email."""
    try:
        res = (_get_client().table("deals")
               .select("deal_id,created_at,status,proposed_value,margin_pct,products,updated_at")
               .ilike("client_email", client_email)
               .order("created_at", desc=True)
               .execute())
        return res.data or []
    except Exception as e:
        print(f"[client_tracker] get_client_deals erro: {e}")
        return []


def bulk_import_clients(rows: list[dict]) -> tuple[int, int]:
    """
    Importação em massa. Cada dict deve ter pelo menos 'company_name' e 'country'.
    Devolve (inseridos, erros).
    """
    ok = err = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for row in rows:
        try:
            row.setdefault("status", "Ativo")
            row.setdefault("market", "EU")
            row.setdefault("client_type", "Distribuidor")
            row.setdefault("currency", "EUR")
            row.setdefault("brands", [])
            row.setdefault("categories", [])
            row["created_at"] = now
            row["updated_at"] = now
            _get_client().table("clients").insert(row).execute()
            ok += 1
        except Exception as e:
            print(f"[client_tracker] bulk_import erro: {e}")
            err += 1
    return ok, err
