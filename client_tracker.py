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


# ── Tabelas de referência ──────────────────────────────────────────────────────

_EU_COUNTRIES = {
    "Portugal","Spain","France","Germany","Italy","Netherlands","Belgium",
    "Poland","Romania","Bulgaria","Czech Republic","Slovakia","Hungary",
    "Croatia","Slovenia","Greece","Austria","Sweden","Denmark","Finland",
    "Ireland","Luxembourg","Malta","Cyprus","Estonia","Latvia","Lithuania",
}
_AFRICA_COUNTRIES = {
    "Morocco","Algeria","Tunisia","Libya","Egypt","Angola","Mozambique",
    "Nigeria","Kenya","South Africa","Ghana","Senegal","Ivory Coast",
    "Cameroon","Tanzania","Uganda","Ethiopia","Sudan","Cape Verde",
    "Cabo Verde","Madagascar","Rwanda","Zambia","Zimbabwe","Botswana",
}
_MIDDLE_EAST = {
    "UAE","Saudi Arabia","Qatar","Kuwait","Bahrain","Oman","Jordan",
    "Lebanon","Israel","Turkey","Iraq","Iran","Palestine","Yemen",
}

COUNTRY_PHONE_CODES: dict[str, str] = {
    "Portugal": "+351", "Spain": "+34", "France": "+33", "Germany": "+49",
    "Italy": "+39", "Netherlands": "+31", "Belgium": "+32", "Poland": "+48",
    "Romania": "+40", "Bulgaria": "+359", "Czech Republic": "+420",
    "Slovakia": "+421", "Hungary": "+36", "Croatia": "+385",
    "Slovenia": "+386", "Greece": "+30", "Austria": "+43", "Sweden": "+46",
    "Denmark": "+45", "Finland": "+358", "Norway": "+47", "Switzerland": "+41",
    "United Kingdom": "+44", "UK": "+44", "Ireland": "+353",
    "Estonia": "+372", "Latvia": "+371", "Lithuania": "+370",
    "Luxembourg": "+352", "Malta": "+356", "Cyprus": "+357",
    "Morocco": "+212", "Algeria": "+213", "Tunisia": "+216",
    "Angola": "+244", "Mozambique": "+258", "Nigeria": "+234",
    "Kenya": "+254", "South Africa": "+27", "Ghana": "+233",
    "Senegal": "+221", "Cape Verde": "+238", "Cabo Verde": "+238",
    "UAE": "+971", "Saudi Arabia": "+966", "Qatar": "+974",
    "Kuwait": "+965", "Israel": "+972", "Turkey": "+90",
    "Russia": "+7", "Ukraine": "+380", "Serbia": "+381",
    "Albania": "+355", "Bosnia": "+387", "North Macedonia": "+389",
    "Montenegro": "+382", "Kosovo": "+383",
}


# ── Qualidade de Dados ─────────────────────────────────────────────────────────

def data_quality_report() -> dict:
    """
    Analisa a qualidade dos dados e devolve um relatório com:
    - email_domain_issues: empresas com contactos de domínios diferentes
    - phone_issues:        telefones sem indicativo de país
    - duplicates:          grupos de empresas com nomes similares
    - missing_fields:      registos com campos importantes em falta
    """
    from collections import defaultdict
    from difflib import SequenceMatcher

    clients = _get_client().table("clients").select("*").execute().data or []

    # 1. Domínios de email por empresa
    company_emails: dict[str, list] = defaultdict(list)
    for c in clients:
        cn = (c.get("company_name") or "").strip()
        em = (c.get("contact_email") or "").strip()
        if cn and em and "@" in em:
            domain = em.split("@", 1)[1].lower()
            company_emails[cn].append({"id": c["id"], "email": em, "domain": domain})

    email_issues = []
    for company, entries in company_emails.items():
        domains = {e["domain"] for e in entries}
        if len(domains) > 1:
            email_issues.append({"company": company, "entries": entries,
                                  "domains": sorted(domains)})

    # 2. Telefones sem indicativo (+)
    phone_issues = []
    for c in clients:
        phone = (c.get("contact_phone") or "").strip()
        if phone and not phone.startswith("+"):
            country = c.get("country", "")
            suggested = COUNTRY_PHONE_CODES.get(country, "")
            phone_issues.append({
                "id":        c["id"],
                "company":   c.get("company_name", "—"),
                "contact":   c.get("contact_name", "—"),
                "phone":     phone,
                "country":   country,
                "suggested": suggested,
            })

    # 3. Empresas duplicadas (SequenceMatcher > 0.82)
    name_index = [(c["id"], (c.get("company_name") or "").strip().lower())
                  for c in clients if c.get("company_name")]
    checked, dup_groups = set(), []
    for i, (id1, n1) in enumerate(name_index):
        if id1 in checked or not n1:
            continue
        group_ids = [id1]
        for j, (id2, n2) in enumerate(name_index):
            if i >= j or id2 in checked or not n2:
                continue
            if SequenceMatcher(None, n1, n2).ratio() > 0.82:
                group_ids.append(id2)
        if len(group_ids) > 1:
            for gid in group_ids:
                checked.add(gid)
            dup_groups.append([c for c in clients if c["id"] in group_ids])

    # 4. Campos importantes em falta
    important = ["company_name", "country", "contact_email", "contact_phone",
                 "client_type", "market"]
    missing_fields = []
    for c in clients:
        missing = [f for f in important if not c.get(f)]
        if missing:
            missing_fields.append({
                "id":      c["id"],
                "company": c.get("company_name", "—"),
                "missing": missing,
            })

    return {
        "email_domain_issues": email_issues,
        "phone_issues":        phone_issues,
        "duplicates":          dup_groups,
        "missing_fields":      missing_fields,
        "total_clients":       len(clients),
    }


def fix_phone_add_code(client_id: str, phone: str, country: str) -> bool:
    """Adiciona o indicativo do país ao número de telefone se ainda não tiver."""
    code = COUNTRY_PHONE_CODES.get(country, "")
    if not code or phone.startswith("+"):
        return False
    clean = phone.lstrip("0").strip()
    new_phone = f"{code} {clean}"
    return update_client(client_id, {"contact_phone": new_phone})


def fix_all_phones() -> tuple[int, int]:
    """Aplica indicativo de país em todos os telefones que não o têm. Devolve (fixed, skipped)."""
    clients = _get_client().table("clients").select(
        "id,contact_phone,country").execute().data or []
    fixed = skipped = 0
    for c in clients:
        phone   = (c.get("contact_phone") or "").strip()
        country = c.get("country", "")
        if phone and not phone.startswith("+"):
            if fix_phone_add_code(str(c["id"]), phone, country):
                fixed += 1
            else:
                skipped += 1
    return fixed, skipped


def merge_clients(primary_id: str, secondary_id: str) -> bool:
    """
    Faz merge de dois registos de clientes.
    O registo primary é enriquecido com campos em falta do secondary.
    O secondary é apagado.
    """
    primary   = get_client(primary_id)
    secondary = get_client(secondary_id)
    if not primary or not secondary:
        return False

    patch: dict = {}
    # Preencher campos em falta no primary com dados do secondary
    for field in ["legal_name","vat","address","zip_code","city","region",
                  "contact_name","contact_role","contact_email","contact_phone",
                  "contact_linkedin","incoterm","payment_terms","currency",
                  "market","client_type","status"]:
        if not primary.get(field) and secondary.get(field):
            patch[field] = secondary[field]

    # Concatenar notas
    p_notes = (primary.get("notes") or "").strip()
    s_notes = (secondary.get("notes") or "").strip()
    if s_notes and s_notes not in p_notes:
        patch["notes"] = f"{p_notes} | {s_notes}".strip(" |")

    # União de brands e categories
    merged_brands = list({*(primary.get("brands") or []),
                           *(secondary.get("brands") or [])})
    merged_cats   = list({*(primary.get("categories") or []),
                           *(secondary.get("categories") or [])})
    if set(merged_brands) != set(primary.get("brands") or []):
        patch["brands"] = merged_brands
    if set(merged_cats) != set(primary.get("categories") or []):
        patch["categories"] = merged_cats

    if patch:
        update_client(primary_id, patch)

    try:
        _get_client().table("clients").delete().eq("id", secondary_id).execute()
        return True
    except Exception as e:
        print(f"[client_tracker] merge_clients erro: {e}")
        return False


def auto_enrich_clients() -> dict:
    """
    Enriquece automaticamente campos deriváveis:
    - market a partir do country
    - currency default EUR
    Devolve {"updated": int, "unchanged": int}.
    """
    clients = _get_client().table("clients").select("*").execute().data or []
    updated = unchanged = 0
    for c in clients:
        patch: dict = {}
        country = (c.get("country") or "").strip()

        # market a partir do country
        if country and not c.get("market"):
            if country in _EU_COUNTRIES:
                patch["market"] = "EU"
            elif country in _AFRICA_COUNTRIES:
                patch["market"] = "África"
            elif country in _MIDDLE_EAST:
                patch["market"] = "Médio Oriente"
            else:
                patch["market"] = "Outros"

        # currency default
        if not c.get("currency"):
            patch["currency"] = "EUR"

        # client_type default
        if not c.get("client_type"):
            patch["client_type"] = "Distribuidor"

        if patch:
            update_client(str(c["id"]), patch)
            updated += 1
        else:
            unchanged += 1

    return {"updated": updated, "unchanged": unchanged}
