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


def find_duplicates(
    email: str = "",
    company_name: str = "",
    vat: str = "",
) -> list:
    """
    Procura possíveis duplicados por email (exacto), nome empresa (fuzzy) ou VAT.
    Devolve lista de dicts com os campos básicos do cliente encontrado.
    """
    results  = []
    seen_ids = set()
    db = _get_client()
    _fields = "id,company_name,contact_name,contact_email,country,status,client_type"

    if email and email.strip():
        res = db.table("clients").select(_fields).ilike("contact_email", email.strip()).execute()
        for r in (res.data or []):
            if r["id"] not in seen_ids:
                results.append(r); seen_ids.add(r["id"])

    if company_name and company_name.strip():
        res = (db.table("clients").select(_fields)
               .ilike("company_name", f"%{company_name.strip()}%").limit(5).execute())
        for r in (res.data or []):
            if r["id"] not in seen_ids:
                results.append(r); seen_ids.add(r["id"])

    if vat and vat.strip():
        res = db.table("clients").select(_fields).eq("vat", vat.strip()).execute()
        for r in (res.data or []):
            if r["id"] not in seen_ids:
                results.append(r); seen_ids.add(r["id"])

    return results


def upsert_from_deal(
    contact_name: str,
    company_name: str,
    email: str,
    country: str,
    incoterm: str = "",
    payment: str = "",
) -> tuple[str, bool]:
    """
    Cria ou enriquece cliente a partir dos dados de um deal.
    - Se o email já existe na BD: preenche apenas campos em falta (não sobrescreve).
    - Se não existe: cria novo registo com os dados disponíveis.
    Devolve (id, True se criado / False se já existia).
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing = get_client_by_email(email) if email else None

    if existing:
        # Enriquecer apenas campos vazios — nunca sobrescrever dados existentes
        updates = {"updated_at": now}
        def _fill(field, value):
            if value and not existing.get(field):
                updates[field] = value
        _fill("contact_name",  contact_name)
        _fill("company_name",  company_name)
        _fill("country",       country)
        _fill("incoterm",      incoterm)
        _fill("payment_terms", payment)
        if len(updates) > 1:
            _get_client().table("clients").update(updates).eq("id", existing["id"]).execute()
        return str(existing["id"]), False
    else:
        cid = add_client({
            "company_name":  company_name or contact_name or "—",
            "contact_name":  contact_name,
            "contact_email": email,
            "country":       country,
            "incoterm":      incoterm,
            "payment_terms": payment,
            "status":        "Ativo",
            "market":        "EU",
            "client_type":   "Distribuidor",
            "brands":        [],
            "categories":    [],
        })
        return cid, True


def sync_clients_from_deals() -> tuple[int, int]:
    """
    Cria entradas no CRM para todos os deals sem cliente correspondente.
    Para deals com email já existente, enriquece os campos em falta.
    Devolve (criados, já_existiam).
    """
    try:
        res = _get_client().table("deals").select(
            "client,company,client_email,country,incoterm,payment_conditions"
        ).execute()
        created = skipped = 0
        for d in (res.data or []):
            em = (d.get("client_email") or "").strip()
            if not em:
                skipped += 1
                continue
            _, is_new = upsert_from_deal(
                contact_name = d.get("client", ""),
                company_name = d.get("company", ""),
                email        = em,
                country      = d.get("country", ""),
                incoterm     = d.get("incoterm", ""),
                payment      = d.get("payment_conditions", ""),
            )
            if is_new:
                created += 1
            else:
                skipped += 1
        return created, skipped
    except Exception as e:
        print(f"[client_tracker] sync_clients_from_deals erro: {e}")
        return 0, 0


def bulk_import_clients(rows: list[dict]) -> tuple[int, int, int]:
    """
    Importação em massa com detecção de duplicados.
    - Se o email já existe: enriquece campos em falta (não duplica).
    - Se não existe: cria novo.
    Devolve (criados, actualizados, erros).
    """
    created = updated = err = 0
    for row in rows:
        try:
            email   = (row.get("contact_email") or "").strip()
            company = (row.get("company_name")  or "").strip()
            existing = get_client_by_email(email) if email else None
            if not existing and company:
                dups = find_duplicates(company_name=company)
                if dups:
                    existing = dups[0]
            if existing:
                now   = datetime.now().strftime("%Y-%m-%d %H:%M")
                patch = {"updated_at": now}
                for field in ("company_name","legal_name","vat","country","market",
                              "address","zip_code","city","contact_name","contact_role",
                              "contact_phone","contact_linkedin","client_type",
                              "incoterm","payment_terms","notes"):
                    if row.get(field) and not existing.get(field):
                        patch[field] = row[field]
                if len(patch) > 1:
                    _get_client().table("clients").update(patch).eq("id", existing["id"]).execute()
                updated += 1
            else:
                row.setdefault("status", "Ativo")
                row.setdefault("market", "EU")
                row.setdefault("client_type", "Distribuidor")
                row.setdefault("currency", "EUR")
                row.setdefault("brands", [])
                row.setdefault("categories", [])
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                row["created_at"] = row["updated_at"] = now
                _get_client().table("clients").insert(row).execute()
                created += 1
        except Exception as e:
            print(f"[client_tracker] bulk_import erro: {e}")
            err += 1
    return created, updated, err
