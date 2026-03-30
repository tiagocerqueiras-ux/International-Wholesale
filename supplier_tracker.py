"""
Supplier Tracker — Supabase CRM Fornecedores
============================================
Gestão centralizada de fornecedores/marcas para BoxMovers Export.
"""

from datetime import datetime
from config import SUPABASE_URL, SUPABASE_KEY

SUPPLIER_STATUSES = ["Ativo", "Em Negociação", "Inativo", "Bloqueado"]
SUPPLIER_TYPES    = ["Fornecedor Direto", "Marca Própria", "Agente", "Distribuidor", "Outro"]
SUPPLIER_MARKETS  = ["EU", "Global", "Portugal", "África", "Médio Oriente"]

CONTACT_ROLES = [
    "Key Account Manager", "Sales Director", "Export Manager",
    "Brand Manager", "Trade Marketing", "Financeiro / Finance",
    "Logística / Logistics", "CEO / Owner", "Assistente Comercial", "Outro",
]

# Categorias e marcas partilhadas com client_tracker
CATEGORIES_LIST = ["SPH", "AUDIO", "MDA", "SDA", "TV", "IT", "FOTO", "GAM", "VC", "OTH"]

BRANDS_LIST = [
    "BABYLISS", "BOSCH", "BRAUN", "CANON", "FUJIFILM", "FUJI INSTAX",
    "BOSE", "GARMIN", "MOULINEX", "KRUPS", "HISENSE", "PHILIPS", "SMEG",
    "PLAYSTATION", "REMINGTON", "RUSSELL HOBBS", "APPLE", "OPPO",
    "GOOGLE PIXEL", "COSORI", "ROWENTA", "TEFAL", "DYSON", "DE'LONGHI",
    "NESPRESSO", "SAMSUNG", "LG", "SONY", "XIAOMI", "OUTRAS",
]

# CGF conhecidos (referência rápida — valores do Business Plan)
CGF_REFERENCE = {
    "BABYLISS": 26.0, "SMEG": 23.3, "FUJIFILM": 15.0, "BOSE": 14.8,
    "BRAUN": 13.73, "CANON": 12.5, "KRUPS": 12.3, "PHILIPS": 8.9,
    "ROWENTA": 8.0, "TEFAL": 8.0, "MOULINEX": 8.0,
}


def _db():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── CRUD ───────────────────────────────────────────────────────────────────────

def add_supplier(data: dict) -> str:
    """Cria fornecedor. Devolve o id gerado."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    row = {
        "supplier_name":   data.get("supplier_name", ""),
        "legal_name":      data.get("legal_name", ""),
        "vat":             data.get("vat", ""),
        "country":         data.get("country", ""),
        "brand":           data.get("brand", ""),
        "brands":          data.get("brands", []),
        "categories":      data.get("categories", []),
        "contact_name":    data.get("contact_name", ""),
        "contact_role":    data.get("contact_role", ""),
        "contact_email":   data.get("contact_email", ""),
        "contact_phone":   data.get("contact_phone", ""),
        "contact_linkedin":data.get("contact_linkedin", ""),
        "contacts":        data.get("contacts", []),
        "cgf":             float(data.get("cgf", 0) or 0),
        "payment_terms":   data.get("payment_terms", ""),
        "incoterm":        data.get("incoterm", ""),
        "currency":        data.get("currency", "EUR"),
        "min_order":       float(data.get("min_order", 0) or 0),
        "lead_time":       data.get("lead_time", ""),
        "supplier_type":   data.get("supplier_type", "Fornecedor Direto"),
        "status":          data.get("status", "Ativo"),
        "notes":           data.get("notes", ""),
        "created_at":      now,
        "updated_at":      now,
    }
    res = _db().table("suppliers").insert(row).execute()
    return str(res.data[0]["id"]) if res.data else ""


def update_supplier(supplier_id: str, data: dict) -> bool:
    try:
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _db().table("suppliers").update(data).eq("id", supplier_id).execute()
        return True
    except Exception as e:
        print(f"[supplier_tracker] update_supplier erro: {e}")
        return False


def get_supplier(supplier_id: str) -> dict | None:
    try:
        res = _db().table("suppliers").select("*").eq("id", supplier_id).single().execute()
        return res.data or None
    except Exception as e:
        print(f"[supplier_tracker] get_supplier erro: {e}")
        return None


def get_supplier_by_email(email: str) -> dict | None:
    try:
        res = (_db().table("suppliers")
               .select("*").ilike("contact_email", email).limit(1).execute())
        return res.data[0] if res.data else None
    except Exception:
        return None


def get_supplier_by_brand(brand: str) -> dict | None:
    try:
        res = (_db().table("suppliers")
               .select("*").ilike("brand", brand).limit(1).execute())
        return res.data[0] if res.data else None
    except Exception:
        return None


def list_suppliers(
    status: str = None,
    supplier_type: str = None,
    brand: str = None,
    country: str = None,
    search: str = None,
) -> list:
    try:
        q = _db().table("suppliers").select(
            "id,supplier_name,brand,brands,country,contact_name,contact_email,"
            "contact_phone,supplier_type,status,cgf,categories,incoterm,"
            "payment_terms,notes,created_at,updated_at"
        ).order("supplier_name")
        if status:        q = q.eq("status", status)
        if supplier_type: q = q.eq("supplier_type", supplier_type)
        if brand:         q = q.ilike("brand", f"%{brand}%")
        if country:       q = q.ilike("country", f"%{country}%")
        if search:        q = q.ilike("supplier_name", f"%{search}%")
        res = q.execute()
        return res.data or []
    except Exception as e:
        print(f"[supplier_tracker] list_suppliers erro: {e}")
        return []


def count_suppliers() -> int:
    try:
        res = _db().table("suppliers").select("id", count="exact").execute()
        return res.count or 0
    except Exception:
        return 0


def delete_supplier(supplier_id: str) -> bool:
    try:
        _db().table("suppliers").delete().eq("id", supplier_id).execute()
        return True
    except Exception as e:
        print(f"[supplier_tracker] delete_supplier erro: {e}")
        return False


def find_duplicate_suppliers(
    email: str = "",
    supplier_name: str = "",
    brand: str = "",
) -> list:
    """Procura possíveis duplicados por email, nome ou marca principal."""
    results  = []
    seen_ids = set()
    db = _db()
    _fields = "id,supplier_name,brand,contact_name,contact_email,country,status"

    if email and email.strip():
        res = db.table("suppliers").select(_fields).ilike("contact_email", email.strip()).execute()
        for r in (res.data or []):
            if r["id"] not in seen_ids:
                results.append(r); seen_ids.add(r["id"])

    if supplier_name and supplier_name.strip():
        res = (db.table("suppliers").select(_fields)
               .ilike("supplier_name", f"%{supplier_name.strip()}%").limit(5).execute())
        for r in (res.data or []):
            if r["id"] not in seen_ids:
                results.append(r); seen_ids.add(r["id"])

    if brand and brand.strip():
        res = (db.table("suppliers").select(_fields)
               .ilike("brand", f"%{brand.strip()}%").limit(5).execute())
        for r in (res.data or []):
            if r["id"] not in seen_ids:
                results.append(r); seen_ids.add(r["id"])

    return results


# ── Contactos (JSONB) ──────────────────────────────────────────────────────────

def get_supplier_contacts(supplier_id: str) -> list:
    """
    Devolve a lista de contactos do fornecedor.
    Auto-migra contacto individual para JSONB se necessário.
    """
    supplier = get_supplier(supplier_id)
    if not supplier:
        return []

    contacts = supplier.get("contacts") or []

    if not contacts:
        name  = supplier.get("contact_name", "").strip()
        email = supplier.get("contact_email", "").strip()
        if name or email:
            contacts = [{
                "name":     name,
                "role":     supplier.get("contact_role", ""),
                "email":    email,
                "phone":    supplier.get("contact_phone", ""),
                "linkedin": supplier.get("contact_linkedin", ""),
                "primary":  True,
                "notes":    "",
            }]
            _db().table("suppliers").update({"contacts": contacts}).eq("id", supplier_id).execute()

    has_primary = any(c.get("primary") for c in contacts)
    if contacts and not has_primary:
        contacts[0]["primary"] = True
        _db().table("suppliers").update({"contacts": contacts}).eq("id", supplier_id).execute()

    return contacts


def save_supplier_contacts(supplier_id: str, contacts: list) -> bool:
    """Guarda contactos e sincroniza campos individuais com o primary."""
    if not contacts:
        return update_supplier(supplier_id, {"contacts": []})

    primaries = [i for i, c in enumerate(contacts) if c.get("primary")]
    if not primaries:
        contacts[0]["primary"] = True
    elif len(primaries) > 1:
        for i, c in enumerate(contacts):
            c["primary"] = (i == primaries[0])

    primary = next((c for c in contacts if c.get("primary")), contacts[0])
    patch = {
        "contacts":          contacts,
        "contact_name":      primary.get("name", ""),
        "contact_role":      primary.get("role", ""),
        "contact_email":     primary.get("email", ""),
        "contact_phone":     primary.get("phone", ""),
        "contact_linkedin":  primary.get("linkedin", ""),
        "updated_at":        datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    try:
        _db().table("suppliers").update(patch).eq("id", supplier_id).execute()
        return True
    except Exception as e:
        print(f"[supplier_tracker] save_supplier_contacts erro: {e}")
        return False


# ── Qualidade de Dados ─────────────────────────────────────────────────────────

def supplier_quality_report() -> dict:
    """
    Analisa a qualidade dos dados dos fornecedores:
    - phone_issues:     telefones sem indicativo
    - duplicates:       fornecedores com nomes similares
    - missing_fields:   registos com campos importantes em falta
    - no_cgf:           fornecedores sem CGF definido
    """
    from difflib import SequenceMatcher
    from client_tracker import COUNTRY_PHONE_CODES

    suppliers = _db().table("suppliers").select("*").execute().data or []

    # 1. Telefones sem indicativo
    phone_issues = []
    for s in suppliers:
        phone = (s.get("contact_phone") or "").strip()
        if phone and not phone.startswith("+"):
            country   = s.get("country", "")
            suggested = COUNTRY_PHONE_CODES.get(country, "")
            phone_issues.append({
                "id":        s["id"],
                "supplier":  s.get("supplier_name", "—"),
                "contact":   s.get("contact_name", "—"),
                "phone":     phone,
                "country":   country,
                "suggested": suggested,
            })

    # 2. Duplicados por nome (SequenceMatcher > 0.82)
    name_index = [(s["id"], (s.get("supplier_name") or "").strip().lower())
                  for s in suppliers if s.get("supplier_name")]
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
            dup_groups.append([s for s in suppliers if s["id"] in group_ids])

    # 3. Campos importantes em falta
    important = ["supplier_name", "brand", "contact_email", "cgf", "supplier_type"]
    missing_fields = []
    for s in suppliers:
        missing = [f for f in important if not s.get(f)]
        if missing:
            missing_fields.append({
                "id":       s["id"],
                "supplier": s.get("supplier_name", "—"),
                "missing":  missing,
            })

    # 4. Fornecedores sem CGF
    no_cgf = [
        {"id": s["id"], "supplier": s.get("supplier_name","—"), "brand": s.get("brand","—")}
        for s in suppliers if not s.get("cgf")
    ]

    return {
        "phone_issues":   phone_issues,
        "duplicates":     dup_groups,
        "missing_fields": missing_fields,
        "no_cgf":         no_cgf,
        "total":          len(suppliers),
    }


def auto_fill_cgf_from_reference() -> dict:
    """
    Preenche automaticamente o CGF para fornecedores cuja marca coincide
    com os valores de referência do Business Plan.
    Devolve {"updated": int, "skipped": int}.
    """
    suppliers = _db().table("suppliers").select("id,brand,cgf").execute().data or []
    updated = skipped = 0
    for s in suppliers:
        if s.get("cgf"):
            skipped += 1
            continue
        brand_upper = (s.get("brand") or "").strip().upper()
        ref_cgf = CGF_REFERENCE.get(brand_upper)
        if ref_cgf:
            update_supplier(str(s["id"]), {"cgf": ref_cgf})
            updated += 1
        else:
            skipped += 1
    return {"updated": updated, "skipped": skipped}


def merge_suppliers(primary_id: str, secondary_id: str) -> bool:
    """
    Faz merge de dois registos de fornecedores.
    Primary é enriquecido, secondary é apagado.
    """
    primary   = get_supplier(primary_id)
    secondary = get_supplier(secondary_id)
    if not primary or not secondary:
        return False

    patch: dict = {}
    for field in ["legal_name", "vat", "country", "brand", "contact_name", "contact_role",
                  "contact_email", "contact_phone", "contact_linkedin",
                  "cgf", "payment_terms", "incoterm", "currency", "min_order",
                  "lead_time", "supplier_type", "status"]:
        if not primary.get(field) and secondary.get(field):
            patch[field] = secondary[field]

    # União de brands e categories
    merged_brands = list({*(primary.get("brands") or []), *(secondary.get("brands") or [])})
    merged_cats   = list({*(primary.get("categories") or []), *(secondary.get("categories") or [])})
    if set(merged_brands) != set(primary.get("brands") or []):
        patch["brands"] = merged_brands
    if set(merged_cats) != set(primary.get("categories") or []):
        patch["categories"] = merged_cats

    # União de contactos JSONB
    p_contacts = primary.get("contacts") or []
    s_contacts = secondary.get("contacts") or []
    p_emails   = {c.get("email","").lower() for c in p_contacts}
    for sc in s_contacts:
        if sc.get("email","").lower() not in p_emails:
            sc["primary"] = False
            p_contacts.append(sc)
    if len(p_contacts) != len(primary.get("contacts") or []):
        patch["contacts"] = p_contacts

    # Concatenar notas
    p_notes = (primary.get("notes") or "").strip()
    s_notes = (secondary.get("notes") or "").strip()
    if s_notes and s_notes not in p_notes:
        patch["notes"] = f"{p_notes} | {s_notes}".strip(" |")

    if patch:
        update_supplier(primary_id, patch)

    try:
        _db().table("suppliers").delete().eq("id", secondary_id).execute()
        return True
    except Exception as e:
        print(f"[supplier_tracker] merge_suppliers erro: {e}")
        return False


def get_supplier_deals(supplier_name: str, brand: str = "") -> list:
    """
    Devolve deals que mencionam este fornecedor em supplier_ids.
    Útil para ver encomendas em curso e histórico por fornecedor.
    """
    try:
        from deal_tracker import _get_client as _dt_client
        search_terms = list({t.strip() for t in [brand, supplier_name] if t.strip()})
        all_results  = []
        seen_ids     = set()
        for term in search_terms:
            res = (_dt_client().table("deals")
                   .select("deal_id,client,country,status,proposed_value,"
                           "order_date,expected_delivery,actual_delivery,"
                           "invoice_number,invoice_value,updated_at,supplier_ids")
                   .ilike("supplier_ids", f"%{term}%")
                   .order("updated_at", desc=True)
                   .execute())
            for r in (res.data or []):
                if r.get("deal_id") not in seen_ids:
                    all_results.append(r)
                    seen_ids.add(r["deal_id"])
        all_results.sort(key=lambda x: x.get("updated_at",""), reverse=True)
        return all_results
    except Exception as e:
        print(f"[supplier_tracker] get_supplier_deals erro: {e}")
        return []


def get_cgf_dashboard_data() -> list:
    """
    Para cada fornecedor com CGF > 0, calcula a estimativa de rebate
    com base nos deals registados com esse fornecedor em supplier_ids.
    Devolve lista de dicts ordenada por planned_rebate desc.
    """
    try:
        from deal_tracker import _get_client as _dt_client
        from config import PIPELINE_CLOSED_STATUSES

        suppliers = (_db().table("suppliers")
                     .select("id,supplier_name,brand,cgf,status")
                     .gt("cgf", 0)
                     .execute().data or [])

        all_deals = (_dt_client().table("deals")
                     .select("deal_id,supplier_ids,proposed_value,invoice_value,status")
                     .execute().data or [])

        rows = []
        for s in suppliers:
            brand = (s.get("brand") or "").strip()
            name  = (s.get("supplier_name") or "").strip()
            cgf   = float(s.get("cgf") or 0)
            search_terms = list({t.lower() for t in [brand, name] if t})

            linked_ids: set = set()
            for d in all_deals:
                sup_ids = (d.get("supplier_ids") or "").lower()
                if any(t in sup_ids for t in search_terms):
                    linked_ids.add(d["deal_id"])

            linked = [d for d in all_deals if d.get("deal_id") in linked_ids]
            closed = [d for d in linked if d.get("status") in PIPELINE_CLOSED_STATUSES]
            active = [d for d in linked if d.get("status") not in PIPELINE_CLOSED_STATUSES]

            def _sum_val(deals_list: list) -> float:
                return sum(
                    float(d.get("invoice_value") or d.get("proposed_value") or 0)
                    for d in deals_list
                )

            closed_val  = round(_sum_val(closed), 2)
            active_val  = round(_sum_val(active), 2)
            planned_reb = round((closed_val + active_val) * cgf / 100, 2)
            closed_reb  = round(closed_val * cgf / 100, 2)

            rows.append({
                "supplier":       name,
                "brand":          brand,
                "cgf_pct":        cgf,
                "active_deals":   len(active),
                "active_value":   active_val,
                "closed_deals":   len(closed),
                "closed_value":   closed_val,
                "planned_rebate": planned_reb,
                "closed_rebate":  closed_reb,
            })

        rows.sort(key=lambda x: -x["planned_rebate"])
        return rows
    except Exception as e:
        print(f"[supplier_tracker] get_cgf_dashboard_data erro: {e}")
        return []
