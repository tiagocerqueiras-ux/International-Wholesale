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
            "id,company_name,country,market,contact_name,contact_email,contact_phone,"
            "client_type,status,brands,categories,incoterm,payment_terms,"
            "notes,created_at,updated_at"
        ).order("company_name")
        if status:      q = q.eq("status", status)
        if market:      q = q.eq("market", market)
        if country:     q = q.ilike("country", f"%{country}%")
        if client_type: q = q.eq("client_type", client_type)
        if search:
            # Pesquisar em company_name, contact_name e contact_email (OR)
            s = search.replace("%", "").replace("'", "")
            q = q.or_(
                f"company_name.ilike.%{s}%,"
                f"contact_name.ilike.%{s}%,"
                f"contact_email.ilike.%{s}%"
            )
        res = q.execute()
        return res.data or []
    except Exception as e:
        print(f"[client_tracker] list_clients erro: {e}")
        return []


def get_company_names() -> list[str]:
    """Devolve lista ordenada de nomes de empresas — usado para autocomplete."""
    try:
        res = (_get_client().table("clients")
               .select("company_name")
               .order("company_name")
               .execute())
        return [r["company_name"] for r in (res.data or []) if r.get("company_name")]
    except Exception:
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


# ── Múltiplos Contactos ────────────────────────────────────────────────────────

CONTACT_ROLES = [
    "Compras / Procurement", "Diretor Comercial", "CEO / Owner",
    "Financeiro / Finance", "Logística / Logistics", "Marketing",
    "Responsável de Conta", "Técnico / IT", "Outro",
]


def get_contacts(client_id: str) -> list:
    """
    Devolve a lista de contactos de um cliente.
    Se contacts JSONB estiver vazio, auto-migra o contacto principal existente.
    Garante que sempre existe exatamente 1 contacto marcado como primary.
    """
    client = get_client(client_id)
    if not client:
        return []

    contacts = client.get("contacts") or []

    # Auto-migração: se não há contactos mas existem campos individuais
    if not contacts:
        name  = client.get("contact_name", "").strip()
        email = client.get("contact_email", "").strip()
        if name or email:
            contacts = [{
                "name":      name,
                "role":      client.get("contact_role", ""),
                "email":     email,
                "phone":     client.get("contact_phone", ""),
                "linkedin":  client.get("contact_linkedin", ""),
                "primary":   True,
                "notes":     "",
            }]
            # Persistir a migração
            _get_client().table("clients").update({"contacts": contacts}).eq("id", client_id).execute()

    # Garantir que há sempre um primary
    has_primary = any(c.get("primary") for c in contacts)
    if contacts and not has_primary:
        contacts[0]["primary"] = True
        _get_client().table("clients").update({"contacts": contacts}).eq("id", client_id).execute()

    return contacts


def save_contacts(client_id: str, contacts: list) -> bool:
    """
    Guarda a lista de contactos e sincroniza os campos individuais
    com o contacto marcado como primary.
    """
    if not contacts:
        return update_client(client_id, {"contacts": []})

    # Garantir exatamente 1 primary
    primaries = [i for i, c in enumerate(contacts) if c.get("primary")]
    if not primaries:
        contacts[0]["primary"] = True
    elif len(primaries) > 1:
        for i, c in enumerate(contacts):
            c["primary"] = (i == primaries[0])

    # Sincronizar campos individuais com o primary
    primary = next((c for c in contacts if c.get("primary")), contacts[0])
    patch = {
        "contacts":         contacts,
        "contact_name":     primary.get("name", ""),
        "contact_role":     primary.get("role", ""),
        "contact_email":    primary.get("email", ""),
        "contact_phone":    primary.get("phone", ""),
        "contact_linkedin": primary.get("linkedin", ""),
        "updated_at":       datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    try:
        _get_client().table("clients").update(patch).eq("id", client_id).execute()
        return True
    except Exception as e:
        print(f"[client_tracker] save_contacts erro: {e}")
        return False


def enrich_brands_from_deals(client_email: str) -> dict:
    """
    Analisa o histórico de deals do cliente e extrai marcas e categorias
    a partir dos SKUs encontrados nos deals (campo sku_ids).
    Devolve {"brands_added": int, "categories_added": int}.
    """
    from sku_lookup import build_cache

    if not client_email:
        return {"brands_added": 0, "categories_added": 0}

    client = get_client_by_email(client_email)
    if not client:
        return {"brands_added": 0, "categories_added": 0}

    # Carregar cache de SKUs
    try:
        cache = build_cache()
    except Exception:
        cache = {}

    # Buscar deals com sku_ids
    try:
        res = (_get_client().table("deals")
               .select("sku_ids")
               .ilike("client_email", client_email)
               .execute())
        deals_raw = res.data or []
    except Exception:
        deals_raw = []

    found_brands:     set = set()
    found_categories: set = set()

    _brands_upper = {b.upper(): b for b in BRANDS_LIST}  # lookup rápido

    for deal in deals_raw:
        sku_ids_str = (deal.get("sku_ids") or "").strip()
        if not sku_ids_str:
            continue
        # sku_ids é armazenado como "SKU1, SKU2, SKU3"
        for sku_code in [s.strip() for s in sku_ids_str.split(",") if s.strip()]:
            sku_info = cache.get(str(sku_code), {})
            brand = (sku_info.get("brand") or "").strip().upper()
            cat   = (sku_info.get("cat") or "").strip().upper()
            matched_brand = _brands_upper.get(brand)
            if matched_brand:
                found_brands.add(matched_brand)
            if cat and cat in CATEGORIES_LIST:
                found_categories.add(cat)

    # União com existentes
    existing_brands = set(client.get("brands") or [])
    existing_cats   = set(client.get("categories") or [])
    new_brands      = found_brands - existing_brands
    new_cats        = found_categories - existing_cats

    if new_brands or new_cats:
        update_client(str(client["id"]), {
            "brands":     sorted(existing_brands | found_brands),
            "categories": sorted(existing_cats   | found_categories),
        })

    return {"brands_added": len(new_brands), "categories_added": len(new_cats)}


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


# ── KPIs de Performance ────────────────────────────────────────────────────────

def get_client_kpis(client_email: str) -> dict:
    """
    Agrega KPIs de performance a partir do histórico de deals do cliente.
    Devolve: total_revenue, avg_margin, deal_count, closed_deals,
             active_deals, last_deal_date, active_pipeline_value.
    """
    try:
        res = (_get_client().table("deals")
               .select("deal_id,created_at,status,proposed_value,margin_pct")
               .ilike("client_email", client_email)
               .execute())
        deals = res.data or []
    except Exception:
        deals = []

    total_revenue      = 0.0
    active_pipeline    = 0.0
    margins_closed     = []
    closed_deals       = 0
    active_deals       = 0
    last_deal_date     = None

    _active_statuses   = {"Rascunho","Enviado","Em Negociação","Follow-up","Lead","Pedido de Cotação"}
    _closed_statuses   = {"Faturado","Fechado","Encomenda Confirmada","Em Preparação","Expedido","Entregue"}

    for d in deals:
        val    = float(d.get("proposed_value") or 0)
        # margin_pct pode vir como "9.9%" (string) ou float — normalizar
        _mpct_raw = str(d.get("margin_pct") or "0").replace("%","").strip()
        try:
            pct = float(_mpct_raw)
        except (ValueError, TypeError):
            pct = 0.0
        status = d.get("status","")
        date   = (d.get("created_at") or "")[:10]

        if status in _closed_statuses:
            total_revenue += val
            closed_deals  += 1
            if pct > 0:
                margins_closed.append(pct)
        elif status in _active_statuses:
            active_deals    += 1
            active_pipeline += val

        if date and (last_deal_date is None or date > last_deal_date):
            last_deal_date = date

    avg_margin = round(sum(margins_closed) / len(margins_closed), 1) if margins_closed else 0.0

    return {
        "total_revenue":    round(total_revenue, 2),
        "avg_margin":       avg_margin,
        "deal_count":       len(deals),
        "closed_deals":     closed_deals,
        "active_deals":     active_deals,
        "active_pipeline":  round(active_pipeline, 2),
        "last_deal_date":   last_deal_date or "—",
    }


# ── Segmentação Inteligente ────────────────────────────────────────────────────

def smart_segment(
    brands: list = None,
    categories: list = None,
    market: str = None,
    client_type: str = None,
    status_filter: str = "Ativo",
    min_deals: int = 0,
) -> list:
    """
    Rankeia clientes por fit comercial para uma proposta/produto dado.
    Fit Score (0–100):
      - Sobreposição de marcas:     até 40 pontos
      - Sobreposição de categorias: até 30 pontos
      - Atividade (tem deals):      até 20 pontos
      - Match de mercado:           10 pontos
    Devolve lista de dicts ordenada por fit_score desc.
    """
    brands     = [b.upper() for b in (brands or [])]
    categories = [c.upper() for c in (categories or [])]

    try:
        q = _get_client().table("clients").select(
            "id,company_name,country,market,contact_name,contact_email,"
            "client_type,status,brands,categories,incoterm,payment_terms,notes"
        )
        if status_filter:
            q = q.eq("status", status_filter)
        if market:
            q = q.eq("market", market)
        if client_type:
            q = q.eq("client_type", client_type)
        clients_all = q.execute().data or []
    except Exception:
        return []

    # Actividade por email (1 query para todos)
    deal_counts: dict = {}
    try:
        res_d = _get_client().table("deals").select("client_email").execute()
        for row in (res_d.data or []):
            em = (row.get("client_email") or "").lower().strip()
            if em:
                deal_counts[em] = deal_counts.get(em, 0) + 1
    except Exception:
        pass

    results = []
    for c in clients_all:
        c_brands = [b.upper() for b in (c.get("brands") or [])]
        c_cats   = [x.upper() for x in (c.get("categories") or [])]
        c_market = (c.get("market") or "").strip()
        c_email  = (c.get("contact_email") or "").lower().strip()
        n_deals  = deal_counts.get(c_email, 0)

        if n_deals < min_deals:
            continue

        # Brand score
        if brands:
            brand_matches = len(set(brands) & set(c_brands))
            brand_score   = round(min(40, brand_matches / len(brands) * 40))
        else:
            brand_score = 20  # neutro se não há filtro

        # Category score
        if categories:
            cat_matches = len(set(categories) & set(c_cats))
            cat_score   = round(min(30, cat_matches / len(categories) * 30))
        else:
            cat_score = 15  # neutro

        # Activity score
        if n_deals > 5:
            activity_score = 20
        elif n_deals > 0:
            activity_score = 10
        else:
            activity_score = 0

        # Market score
        market_score = 10 if (not market or c_market == market) else 0

        fit_score = brand_score + cat_score + activity_score + market_score

        results.append({
            **c,
            "fit_score":  fit_score,
            "n_deals":    n_deals,
            "brand_score":    brand_score,
            "cat_score":      cat_score,
            "activity_score": activity_score,
        })

    results.sort(key=lambda x: x["fit_score"], reverse=True)
    return results


# ── Documentos KYC ─────────────────────────────────────────────────────────────

def get_client_documents(client_id: str) -> list:
    """Devolve a lista de documentos JSONB do cliente."""
    c = get_client(client_id)
    return (c or {}).get("documents") or []


def add_client_document(
    client_id: str,
    name: str,
    doc_type: str,
    url: str = "",
    notes: str = "",
    file_bytes: bytes = None,
    filename_storage: str = "",
) -> bool:
    """
    Adiciona um documento ao cliente.
    Se file_bytes estiver presente, faz upload para Supabase Storage
    (bucket: client-docs) e guarda a URL pública.
    Caso contrário, guarda apenas os metadados (URL manual).
    """
    from datetime import datetime as _dt
    now = _dt.now().strftime("%Y-%m-%d %H:%M")

    storage_url = url  # default: URL manual

    if file_bytes and filename_storage:
        try:
            _path = f"clients/{client_id}/{filename_storage}"
            _db().storage.from_("client-docs").upload(
                _path, file_bytes,
                file_options={"content-type": "application/octet-stream", "upsert": "true"}
            )
            storage_url = _db().storage.from_("client-docs").get_public_url(_path)
        except Exception as e:
            print(f"[client_tracker] Storage upload erro: {e}")
            # Continua mesmo sem upload — guarda só metadados

    docs = get_client_documents(client_id)
    docs.append({
        "name":        name,
        "type":        doc_type,
        "url":         storage_url,
        "notes":       notes,
        "uploaded_at": now,
    })
    return update_client(client_id, {"documents": docs})


def delete_client_document(client_id: str, doc_index: int) -> bool:
    """Remove o documento na posição doc_index da lista."""
    docs = get_client_documents(client_id)
    if doc_index < 0 or doc_index >= len(docs):
        return False
    _doc = docs[doc_index]
    # Tentar apagar do Storage se tiver URL interna
    if _doc.get("url") and "client-docs" in _doc.get("url",""):
        try:
            _path = f"clients/{client_id}/{_doc['name']}"
            _db().storage.from_("client-docs").remove([_path])
        except Exception:
            pass
    docs.pop(doc_index)
    return update_client(client_id, {"documents": docs})
