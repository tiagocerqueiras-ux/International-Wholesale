"""
client_form.py — Formulário de cliente reutilizável (Fase 1)
=============================================================
Superconjunto: mantém os campos do CRM existente + acrescenta os 13 campos de
onboarding da Fase 1 (contacto financeiro, faturação, IBAN/SWIFT, seguro/limite
de crédito, UBOs, moradas de entrega, documentos).

Usado no CRM (criar/editar) e no fluxo de cliente novo da Nova Cotação.
Documentos guardados localmente em test_docs/ (ambiente de teste).
"""
from pathlib import Path
import streamlit as st

import client_tracker as ct
from config import PAYMENT_CONDITIONS_LIST, INCOTERMS_LIST
from client_tracker import (
    MARKETS, CLIENT_TYPES, CLIENT_STATUSES, BRANDS_LIST, CATEGORIES_LIST,
    find_duplicates,
)

DOCS_DIR = Path(__file__).resolve().parent / "test_docs"
DOC_TYPES = ["pdf", "png", "jpg", "jpeg"]


def _save_upload(uploaded, subdir: str) -> str:
    if not uploaded:
        return ""
    d = DOCS_DIR / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / uploaded.name).write_bytes(uploaded.getbuffer())
    return uploaded.name


def _sel_index(options, value):
    return options.index(value) if value in options else 0


def missing_fields(c: dict) -> list:
    """Devolve a lista de campos de onboarding (Fase 1) ainda por preencher."""
    if not c:
        return []
    checks = {
        "Razão Social": c.get("legal_name"),
        "VAT": c.get("vat"),
        "Certidão Comercial": c.get("commercial_cert_doc"),
        "Morada Fiscal": c.get("address"),
        "Contacto Comercial (nome)": c.get("contact_name"),
        "Tel. Comercial": c.get("contact_phone"),
        "Email Comercial": c.get("contact_email"),
        "Contacto Financeiro (nome)": c.get("fin_contact_name"),
        "Email de faturação": c.get("billing_email"),
        "IBAN": c.get("iban"),
        "SWIFT": c.get("swift"),
        "Comprovativo bancário": c.get("bank_proof_doc"),
        "Condição de pagamento": c.get("payment_terms"),
        "Seguro de crédito": c.get("credit_insurance"),
        "UBOs / Administradores": c.get("ubos"),
        "Moradas de entrega": c.get("delivery_addresses"),
    }
    return [k for k, v in checks.items() if not v]


def render_client_form(prefill: dict | None = None, client_id=None, ns: str = "cli") -> str | None:
    """Renderiza o formulário (criar se client_id None, senão editar).
    Devolve o id do cliente em caso de gravação, senão None.
    """
    p = prefill or {}
    is_new = client_id is None
    k = f"_{ns}_{client_id or 'novo'}"

    with st.form("client_form" + k):
        st.markdown("##### 🏢 Identificação")
        a, b, c = st.columns(3)
        company_name = a.text_input("Nome comercial *", value=p.get("company_name", ""), key="cn"+k)
        legal_name   = b.text_input("Razão Social *",   value=p.get("legal_name", ""),   key="ln"+k)
        vat          = c.text_input("VAT / NIF *",      value=p.get("vat", ""),          key="vat"+k)
        a, b, c = st.columns(3)
        country     = a.text_input("País *", value=p.get("country", ""), key="ct"+k)
        market      = b.selectbox("Mercado", MARKETS, index=_sel_index(MARKETS, p.get("market")), key="mk"+k)
        client_type = c.selectbox("Tipo de Cliente", CLIENT_TYPES, index=_sel_index(CLIENT_TYPES, p.get("client_type")), key="tp"+k)

        st.markdown("##### 📍 Morada Fiscal")
        a, b, c, d = st.columns([4, 1.5, 2, 2])
        address  = a.text_input("Morada",        value=p.get("address", ""),  key="ad"+k)
        zip_code = b.text_input("Código Postal", value=p.get("zip_code", ""), key="zp"+k)
        city     = c.text_input("Cidade",        value=p.get("city", ""),     key="cy"+k)
        region   = d.text_input("Região",        value=p.get("region", ""),   key="rg"+k)

        st.markdown("##### 👥 Contactos")
        col_com, col_fin = st.columns(2)
        with col_com:
            st.markdown("**Comercial**")
            contact_name  = st.text_input("Nome",     value=p.get("contact_name", ""),  key="comn"+k)
            contact_phone = st.text_input("Telefone", value=p.get("contact_phone", ""), key="comt"+k)
            contact_email = st.text_input("Email",    value=p.get("contact_email", ""), key="come"+k)
            contact_role  = st.text_input("Cargo",    value=p.get("contact_role", ""),  key="comr"+k)
        with col_fin:
            st.markdown("**Financeiro**")
            fin_contact_name  = st.text_input("Nome",     value=p.get("fin_contact_name", ""),  key="finn"+k)
            fin_contact_phone = st.text_input("Telefone", value=p.get("fin_contact_phone", ""), key="fint"+k)
            fin_contact_email = st.text_input("Email",    value=p.get("fin_contact_email", ""), key="fine"+k)
            contact_linkedin  = st.text_input("LinkedIn", value=p.get("contact_linkedin", ""),  key="lnk"+k)

        st.markdown("##### 💳 Faturação & Dados bancários")
        a, b, c, d = st.columns([2, 2, 1.3, 1])
        billing_email = a.text_input("Email de faturação", value=p.get("billing_email", ""), key="be"+k)
        iban          = b.text_input("IBAN",  value=p.get("iban", ""),  key="ib"+k)
        swift         = c.text_input("SWIFT/BIC", value=p.get("swift", ""), key="sw"+k)
        currency      = d.selectbox("Moeda", ["EUR", "USD", "GBP", "CHF"],
                                    index=_sel_index(["EUR", "USD", "GBP", "CHF"], p.get("currency") or "EUR"), key="cu"+k)

        st.markdown("##### 📑 Condições comerciais")
        a, b, c, d = st.columns([2.2, 2, 1.6, 1.4])
        incoterm = a.selectbox("Incoterm", INCOTERMS_LIST, index=_sel_index(INCOTERMS_LIST, p.get("incoterm")), key="inc"+k)
        payment_terms = b.selectbox("Condição de pagamento", PAYMENT_CONDITIONS_LIST,
                                    index=_sel_index(PAYMENT_CONDITIONS_LIST, p.get("payment_terms")), key="pt"+k)
        credit_insurance = c.text_input("Seguro de crédito", value=p.get("credit_insurance", ""), key="ci"+k)
        credit_limit = d.number_input("Limite crédito (€)", min_value=0.0, step=1000.0,
                                      value=float(p.get("credit_limit") or 0), key="climit"+k)

        st.markdown("##### 🏷️ Especialização")
        a, b = st.columns(2)
        brands     = a.multiselect("Marcas de interesse", BRANDS_LIST, default=[x for x in (p.get("brands") or []) if x in BRANDS_LIST], key="br"+k)
        categories = b.multiselect("Categorias", CATEGORIES_LIST, default=[x for x in (p.get("categories") or []) if x in CATEGORIES_LIST], key="cat"+k)

        st.markdown("##### 🧑‍⚖️ UBOs e Administradores")
        ubos = st.data_editor(p.get("ubos") or [{"name": "", "role": "", "ownership_pct": 0, "doc": ""}],
            num_rows="dynamic", use_container_width=True, key="ubos"+k,
            column_config={"name": "Nome", "role": "Função (UBO/Admin)",
                           "ownership_pct": st.column_config.NumberColumn("% Capital", min_value=0, max_value=100),
                           "doc": "Documento (nome)"})

        st.markdown("##### 🚚 Moradas de entrega")
        deliveries = st.data_editor(p.get("delivery_addresses") or [{"label": "", "address": "", "zip": "", "city": "", "country": ""}],
            num_rows="dynamic", use_container_width=True, key="dl"+k,
            column_config={"label": "Etiqueta", "address": "Morada", "zip": "C.Postal", "city": "Cidade", "country": "País"})

        st.markdown("##### 📎 Documentos")
        existing = p.get("documents") or []
        if existing:
            st.caption("Já carregados: " + " · ".join(f"{x.get('type')}={x.get('file')}" for x in existing))
        a, b = st.columns(2)
        cert_file = a.file_uploader("Certidão Comercial", type=DOC_TYPES, key="cf"+k)
        bank_file = b.file_uploader("Comprovativo bancário", type=DOC_TYPES, key="bf"+k)
        ubo_files = st.file_uploader("Documentos dos UBOs", type=DOC_TYPES, accept_multiple_files=True, key="uf"+k)

        status = st.selectbox("Status", CLIENT_STATUSES, index=_sel_index(CLIENT_STATUSES, p.get("status") or "Ativo"), key="st"+k)
        notes  = st.text_area("Notas", value=p.get("notes", ""), height=70, key="nt"+k)

        submitted = st.form_submit_button("💾 " + ("Criar cliente" if is_new else "Guardar alterações"),
                                          use_container_width=True, type="primary")

    if not submitted:
        return None

    miss = [n for n, v in [("Nome comercial", company_name), ("Razão Social", legal_name),
                           ("VAT", vat), ("País", country)] if not str(v).strip()]
    if miss:
        st.error("Faltam campos obrigatórios: " + ", ".join(miss))
        return None

    # duplicados (aviso não bloqueante) — só ao criar
    if is_new:
        dups = find_duplicates(email=contact_email, company_name=company_name, vat=vat)
        if dups:
            st.warning("⚠️ Possíveis duplicados: " + " · ".join(
                f"{d.get('company_name','—')} ({d.get('contact_email','—')})" for d in dups[:3]))

    subdir = (vat or company_name).strip().replace("/", "-") or "sem_id"
    cert_doc = _save_upload(cert_file, subdir) or p.get("commercial_cert_doc", "")
    bank_doc = _save_upload(bank_file, subdir) or p.get("bank_proof_doc", "")
    documents = list(existing)
    if cert_file: documents.append({"type": "certidao", "file": cert_doc})
    if bank_file: documents.append({"type": "comprovativo_bancario", "file": bank_doc})
    documents += [{"type": "ubo", "file": _save_upload(f, subdir)} for f in (ubo_files or [])]

    data = {
        "company_name": company_name, "legal_name": legal_name, "vat": vat, "country": country,
        "market": market, "client_type": client_type, "region": region,
        "address": address, "zip_code": zip_code, "city": city,
        "contact_name": contact_name, "contact_phone": contact_phone, "contact_email": contact_email,
        "contact_role": contact_role, "contact_linkedin": contact_linkedin,
        "fin_contact_name": fin_contact_name, "fin_contact_phone": fin_contact_phone,
        "fin_contact_email": fin_contact_email,
        "billing_email": billing_email, "iban": iban, "swift": swift, "currency": currency,
        "commercial_cert_doc": cert_doc, "bank_proof_doc": bank_doc,
        "incoterm": incoterm, "payment_terms": payment_terms,
        "credit_insurance": credit_insurance, "credit_limit": credit_limit or None,
        "brands": brands, "categories": categories,
        "ubos": [u for u in ubos if (u.get("name") or "").strip()],
        "delivery_addresses": [x for x in deliveries if (x.get("address") or "").strip()],
        "documents": documents, "status": status, "notes": notes,
    }

    if is_new:
        cid = ct.add_client(data)
        if cid:
            st.success(f"✅ Cliente **{company_name}** criado (ID {cid}).")
            return cid
        st.error("Erro ao criar cliente.")
        return None
    else:
        if ct.update_client(str(client_id), data):
            st.success("✅ Dados do cliente atualizados.")
            return str(client_id)
        st.error("Erro ao atualizar.")
        return None
