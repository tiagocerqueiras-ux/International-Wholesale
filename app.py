"""
Cotação Agent — Interface Web (Streamlit)
BoxMovers Export | Worten
"""

import sys
from pathlib import Path
from datetime import datetime

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    STATUSES, STATUS_COLORS,
    INCOTERMS_LIST, PAYMENT_CONDITIONS_LIST, PAYMENT_CONDITIONS_DEFAULT, INCOTERM,
    STOCKS_EMAIL, ADMIN_EMAIL,
    MIN_MARGIN_DEFAULT, TARGET_MARGIN_DEFAULT,
    PIPELINE_ACTIVE_STATUSES, PIPELINE_ORDER_STATUSES, PIPELINE_CLOSED_STATUSES,
    DEAL_STALE_DAYS,
    BP_TARGET_REVENUE, BP_BREAK_EVEN, BP_TARGET_EBITDA,
    BP_TAKE_RATE, BP_OUR_CUT_PCT, BP_FIXED_COSTS,
    BP_SCENARIO_BASE, BP_SCENARIO_OPT,
)
from sku_lookup import lookup_skus, search_by_name, build_cache
from deal_tracker import add_deal, update_status, update_margin, update_deal_prices, duplicate_deal, delete_deal, list_deals, get_deal, deal_products_table, get_sku_price_history, update_deal_operational, get_pipeline_stats, get_executive_dashboard_data
from email_generator import generate_proposal, generate_followup, save_email_html, generate_closing_emails, generate_supplier_request, generate_expedition_confirmation, generate_transport_request
from email_sender import create_draft, build_subject
from client_tracker import (
    add_client, update_client, get_client, get_client_by_email,
    list_clients, count_clients, get_client_deals, bulk_import_clients,
    find_duplicates, upsert_from_deal, sync_clients_from_deals,
    data_quality_report, fix_phone_add_code, fix_all_phones,
    merge_clients, auto_enrich_clients,
    get_contacts, save_contacts, enrich_brands_from_deals,
    get_client_kpis, smart_segment,
    get_client_documents, add_client_document, delete_client_document,
    COUNTRY_PHONE_CODES, CONTACT_ROLES,
    CLIENT_STATUSES, CLIENT_TYPES, MARKETS, BRANDS_LIST, CATEGORIES_LIST,
)
from transport_lookup import load_transport_cache, get_countries, get_cps_for_country, get_quote, build_transport_cache, CARRIERS as TRANSPORT_CARRIERS
from auth_manager import (
    login, has_users, add_user, list_users, update_user, reset_password,
    ROLES, ROLE_LABELS, ROLE_BADGE_COLOR, PAGES_BY_ROLE,
    CAN_SEE_MARGINS, CAN_EDIT_DEALS, OWN_DATA_ONLY,
)

# ── Página ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Cotação Agent — International Wholesale", page_icon="📦",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  [data-testid="stSidebar"] { background: #1F4E79; }
  [data-testid="stSidebar"] * { color: white !important; }
  .warn-box { background:#fff3cd; border-left:4px solid #ffc107;
              padding:8px 12px; border-radius:4px; font-size:13px; margin:4px 0; }
  div[data-testid="stForm"] { border: none !important; }
</style>
""", unsafe_allow_html=True)

STATUS_EMOJI = {
    "Lead":                 "🎯",
    "Pedido de Cotação":    "📩",
    "Rascunho":             "🟡",
    "Enviado":              "📤",
    "Em Negociação":        "🔄",
    "Follow-up":            "🔁",
    "Encomenda Confirmada": "✅",
    "Em Preparação":        "📦",
    "Expedido":             "🚚",
    "Entregue":             "📬",
    "Faturado":             "🧾",
    "Arquivado":            "🗄️",
    "Perdido":              "❌",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="A carregar índice de SKUs...", ttl=3600)
def load_index():
    return build_cache()

@st.cache_data(show_spinner="A carregar tarifas de transporte...", ttl=7200)
def load_transport():
    return load_transport_cache()

def fmt2(v):
    if v is None or v == "": return "—"
    try: return f"{float(v):,.2f} €"
    except: return str(v)

fmt4 = fmt2  # todos os valores mostrados a 2 casas decimais

def calc_pvp(base_fc, margin_mode, margin_val):
    if base_fc is None: return None
    if margin_mode == "Percentagem (%)":
        return round(base_fc * (1 + margin_val / 100), 4)
    return round(base_fc + margin_val, 4)

def margin_pct(cost, pvp):
    if not cost or not pvp or pvp == 0: return 0.0
    return round((pvp - cost) / pvp * 100, 2)

def _clear_state():
    for k in ["product_basket","so_manual","margin_mode","margin_val",
              "margin_override","selected_incoterm","payment_conditions","vat_sel",
              "freight_cost_input","freight_from_sim","sim_quotes_cot",
              "sup_basket","sup_so_manual","sup_pvp_alvo"]:
        st.session_state.pop(k, None)

# ── Dialog aprovação email ────────────────────────────────────────────────────
@st.dialog("📧 Revisão do Email — Aprovação Necessária", width="large")
def email_approval_dialog():
    pending   = st.session_state.get("pending_email", {})
    html_body = pending.get("html_body", "")
    did       = pending.get("deal_id", "")
    to_email  = pending.get("client_email", "")
    language  = pending.get("language", "EN")
    client    = pending.get("client_name", "")
    _company  = pending.get("company", "")

    st.markdown("Revê o email antes de enviar.")
    st.divider()
    st.components.v1.html(html_body, height=520, scrolling=True)
    st.divider()

    subject = build_subject(did, client, language, company=_company)

    _dlg_to  = st.text_input("Para (To)", value=to_email, key="dlg_to")
    _dlg_cc  = st.text_input("CC (opcional)", value="", key="dlg_cc",
                              help="Separa vários emails com ;")
    _dlg_bcc = st.text_input("BCC (opcional)", value="", key="dlg_bcc",
                              help="Separa vários emails com ;")
    st.caption(f"**Assunto:** {subject}")

    c1, c2, c3 = st.columns([3, 2, 2])

    with c1:
        if st.button("🚀  Enviar Email", type="primary", use_container_width=True):
            _cc_list  = [e.strip() for e in _dlg_cc.split(";")  if e.strip()] or None
            _bcc_list = [e.strip() for e in _dlg_bcc.split(";") if e.strip()] or None
            ok, err = create_draft(
                to=_dlg_to, subject=subject, html_body=html_body,
                send=True, cc=_cc_list, bcc=_bcc_list,
            )
            if ok:
                save_email_html(did, html_body, "proposal")
                update_margin(did, pending.get("margin_calc", 0), pending.get("pvp_total", 0))
                update_status(did, "Enviado", "Email enviado via SMTP")
                st.session_state["email_result"] = {"success": True, "deal_id": did,
                                                     "msg": "Email enviado com sucesso!"}
                st.session_state.pop("pending_email", None)
                _clear_state()
                st.rerun()
            else:
                st.error(f"Erro ao enviar: {err}")

    with c2:
        if st.button("🔄  Regenerar", use_container_width=True):
            st.session_state.pop("pending_email", None)
            st.rerun()

    with c3:
        if st.button("❌  Cancelar", use_container_width=True):
            if did: update_status(did, "Rascunho", "Cancelado na revisão")
            st.session_state.pop("pending_email", None)
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# SEGURANÇA — Login multi-utilizador
# ══════════════════════════════════════════════════════════════════════════════
_LOGIN_CSS = """
<style>
  [data-testid="stSidebar"] { display: none; }
  .auth-box { max-width: 400px; margin: 80px auto; padding: 40px 36px;
              border-radius: 10px; box-shadow: 0 4px 24px rgba(0,0,0,.10);
              background: #fff; text-align: center; }
  .auth-box h2 { color: #CC0000; font-size: 22px; margin-bottom: 4px; }
  .auth-box p  { color: #666; font-size: 13px; margin-bottom: 24px; }
</style>
"""

def _show_login():
    """Ecrã de login. Devolve True se autenticado."""
    if st.session_state.get("current_user"):
        return True

    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    st.markdown('<div class="auth-box"><h2>🔐 International Wholesale</h2>'
                '<p>BoxMovers B2B Export — Worten</p></div>', unsafe_allow_html=True)

    # ── Primeiro acesso: sem utilizadores criados ─────────────────────────
    try:
        _no_users = not has_users()
    except Exception:
        _no_users = False

    if _no_users:
        st.info("Primeiro acesso — cria a conta de administrador.")
        col = st.columns([1, 2, 1])[1]
        with col:
            su_name  = st.text_input("Nome completo", key="su_name")
            su_email = st.text_input("Email", key="su_email")
            su_pwd   = st.text_input("Password", type="password", key="su_pwd")
            su_pwd2  = st.text_input("Confirmar password", type="password", key="su_pwd2")
            if st.button("Criar conta Owner →", type="primary", use_container_width=True):
                if not su_name or not su_email or not su_pwd:
                    st.error("Preenche todos os campos.")
                elif su_pwd != su_pwd2:
                    st.error("As passwords não coincidem.")
                else:
                    ok, msg = add_user(su_name, su_email, su_pwd, "owner")
                    if ok:
                        user = login(su_email, su_pwd)
                        st.session_state["current_user"] = user
                        st.rerun()
                    else:
                        st.error(f"Erro: {msg}")
        return False

    # ── Login normal ──────────────────────────────────────────────────────
    col = st.columns([1, 2, 1])[1]
    with col:
        lg_email = st.text_input("Email", key="lg_email",
                                 placeholder="nome@empresa.com")
        lg_pwd   = st.text_input("Password", type="password", key="lg_pwd",
                                 placeholder="••••••••")
        if st.button("Entrar →", type="primary", use_container_width=True):
            user = login(lg_email, lg_pwd)
            if user:
                st.session_state["current_user"] = user
                st.rerun()
            else:
                st.error("Email ou password incorrectos.")
    return False


if not _show_login():
    st.stop()

# ── Utilizador autenticado ────────────────────────────────────────────────────
_cu   = st.session_state["current_user"]
_role = _cu.get("role", "comercial_interno")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📦 International Wholesale")
    st.markdown("**BoxMovers B2B Export**")
    st.markdown("---")

    # Nav filtrado pelo role
    _nav_pages = PAGES_BY_ROLE.get(_role, PAGES_BY_ROLE["comercial_interno"])
    page = st.radio("Nav", _nav_pages,
                    label_visibility="collapsed", key="nav")
    st.markdown("---")

    # Info do utilizador + badge de role
    _badge_color = ROLE_BADGE_COLOR.get(_role, "#333")
    st.markdown(
        f"*{_cu.get('name','—')}*  \n"
        f"*{_cu.get('email','—')}*  \n"
        f'<span style="background:{_badge_color};color:#fff;'
        f'font-size:11px;padding:2px 8px;border-radius:10px;">'
        f'{ROLE_LABELS.get(_role,_role)}</span>',
        unsafe_allow_html=True
    )
    st.markdown("")
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.pop("current_user", None)
        st.rerun()

# ── Resultado de aprovação pendente ──────────────────────────────────────────
if "email_result" in st.session_state and page == "🆕  Nova Cotação":
    r = st.session_state.pop("email_result")
    if r.get("success"):
        msg = r.get("msg", "Email processado.")
        st.success(f"✅ Deal **{r['deal_id']}** — {msg}")

if "pending_email" in st.session_state:
    email_approval_dialog()


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 1 — NOVA COTAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
if page == "🆕  Nova Cotação":
    st.title("🆕 Nova Cotação")

    # ── Prefill a partir do CRM ───────────────────────────────────────────────
    _crm_pre = st.session_state.pop("crm_prefill", {})

    # ── 1. Cliente ────────────────────────────────────────────────────────────
    st.subheader("1. Dados do Cliente")
    c1, c2, c3 = st.columns([2, 2, 1.5])
    client   = c1.text_input("Nome do cliente *", value=_crm_pre.get("client",""), placeholder="Ex: João Silva")
    company  = c2.text_input("Empresa", value=_crm_pre.get("company",""), placeholder="Ex: Geppit Group EOOD")
    country  = c3.text_input("País *", value=_crm_pre.get("country",""), placeholder="Ex: Bulgaria")
    c4, c5 = st.columns([3, 1])
    email    = c4.text_input("Email do cliente *", value=_crm_pre.get("email",""), placeholder="Ex: contact@geppit.eu")
    language = c5.selectbox("Língua", ["EN","PT","ES","FR"])

    # ── Lookup automático no CRM ──────────────────────────────────────────────
    if email and "@" in email:
        _crm_match = get_client_by_email(email)
        if _crm_match:
            _cm = _crm_match
            st.success(
                f"✅ **Cliente encontrado no CRM** — "
                f"{_cm.get('company_name','—')} · {_cm.get('country','—')} · "
                f"{_cm.get('client_type','—')} · Status: {_cm.get('status','—')}"
            )
        else:
            _dups = find_duplicates(company_name=company) if company else []
            if _dups:
                st.warning(
                    f"⚠️ Email não encontrado mas existe empresa semelhante: "
                    + " | ".join(f"{d.get('company_name')} ({d.get('contact_email','')})" for d in _dups[:3])
                )
            else:
                st.info("🆕 Novo cliente — será criado no CRM ao guardar o deal.")

    notes = st.text_area("Notas / instruções adicionais para o email (opcional)", height=55,
        placeholder="Ex: desconto extra 2%, prazo especial...",
        help="Contexto adicional para personalizar o email gerado pelo Claude AI.")
    st.divider()

    # ── 2. Condições Comerciais ───────────────────────────────────────────────
    st.subheader("2. Condições Comerciais")
    cc1, cc2, cc3, cc4 = st.columns([2, 3, 1.5, 1.5])
    with cc1:
        inc_idx = next((i for i,x in enumerate(INCOTERMS_LIST) if "EXW" in x), 0)
        selected_incoterm = st.selectbox("Incoterm *", INCOTERMS_LIST, index=inc_idx)
    with cc2:
        pay_sel = st.selectbox("Condições de Pagamento *", PAYMENT_CONDITIONS_LIST, index=0)
        if pay_sel == "Outra (personalizada)...":
            payment_conditions = st.text_input("Descreve as condições",
                                               placeholder="Ex: 30% adiantamento + saldo contra B/L...")
        else:
            payment_conditions = pay_sel
    with cc3:
        # IVA: Isento por defeito; muda para 23% só se país = Portugal
        _is_pt  = country.strip().upper() in ("PORTUGAL", "PT")
        vat_options = ["Isento — Exportação", "IVA 23% — Portugal"]
        _iva_idx = 1 if _is_pt else 0
        # key muda com país → força reset do widget quando país muda
        _vat_key = f"vat_{'pt' if _is_pt else 'exp'}"
        if _vat_key not in st.session_state:
            st.session_state[_vat_key] = vat_options[_iva_idx]
        vat_sel = st.selectbox("IVA", vat_options,
                               index=_iva_idx,
                               key=_vat_key,
                               help="Portugal: 23% | Internacional: isento por defeito")
        vat_rate = 0.23 if "23%" in vat_sel else 0.0
    with cc4:
        # Pre-fill from simulator if a rate was chosen
        if "freight_from_sim" in st.session_state:
            st.session_state["freight_cost_input"] = st.session_state.pop("freight_from_sim")
        freight_cost = st.number_input(
            "🚚 Frete (€)", min_value=0.0,
            step=50.0, format="%.2f",
            key="freight_cost_input",
            help="Custo de transporte — preenche manualmente ou usa o Simulador abaixo",
        )

    availability = st.text_input(
        "📦 Availability / ETA to Worten",
        placeholder="Ex: Ex-stock | Lead time 3–5 days | ETA 15 Apr 2026",
        help="Disponibilidade ou prazo de entrega a incluir na proposta"
    )

    # ── Mini-simulador de transporte ──────────────────────────────────────────
    with st.expander("🚚 Consultar Simulador de Transporte", expanded=False):
        _sim_tc = load_transport()
        if not _sim_tc or not _sim_tc.get("destinations"):
            st.warning("Cache de transporte não disponível. Vai a **🚚 Logística → Actualizar Cache**.")
        else:
            _sim_countries = get_countries(_sim_tc)
            _ms1, _ms2, _ms3, _ms4 = st.columns([2, 1.5, 1, 1.5])

            # Try to match client country (free-text) to Portuguese transport name
            _country_lower_map = {c.lower(): c for c in _sim_countries}
            _client_ctry_lower = country.strip().lower() if country else ""
            _default_ctry_idx  = 0
            for i, c in enumerate(_sim_countries):
                if c.lower() in _client_ctry_lower or _client_ctry_lower in c.lower():
                    _default_ctry_idx = i
                    break

            _sim_country = _ms1.selectbox(
                "País", _sim_countries,
                index=_default_ctry_idx,
                key="sim_country_cot",
            )
            _sim_cps = get_cps_for_country(_sim_country, _sim_tc)
            _sim_cp  = _ms2.selectbox("Zona Postal", _sim_cps, key="sim_cp_cot") if _sim_cps else None
            _sim_pal = _ms3.number_input("Paletes", min_value=1, max_value=33, value=1, step=1, key="sim_pal_cot")
            _sim_cargo = _ms4.number_input("Valor Carga (€)", min_value=0.0, step=100.0,
                                            value=0.0, key="sim_cargo_cot",
                                            help="Para cálculo do seguro (opcional)")
            _sim_ins = st.checkbox("Incluir seguro no total", value=False, key="sim_ins_cot")

            if _sim_cp and st.button("🔍 Calcular", key="sim_calc_cot", type="secondary"):
                _sim_c_cp = f"{_sim_country}{_sim_cp}"
                _sim_quotes = get_quote(
                    c_cp=_sim_c_cp,
                    n_pallets=int(_sim_pal),
                    cargo_value=float(_sim_cargo),
                    include_insurance=_sim_ins,
                    cache=_sim_tc,
                )
                st.session_state["sim_quotes_cot"] = _sim_quotes

            _sq = st.session_state.get("sim_quotes_cot")
            if _sq is not None:
                if not _sq:
                    st.warning("Sem cotações para este destino/nº de paletes.")
                else:
                    st.markdown(f"**Resultados para {_sim_country} · zona {_sim_cp} · {_sim_pal} paletes:**")
                    for _sq_r in _sq:
                        _sq_col1, _sq_col2, _sq_col3, _sq_col4 = st.columns([2, 1.5, 1.5, 1.5])
                        _sq_col1.markdown(f"**{_sq_r['carrier']}**")
                        _sq_col2.markdown(
                            f"Frete: {_sq_r['freight']:,.2f} €"
                            + (f" + fuel: {_sq_r['fuel']:,.2f} €" if _sq_r['fuel'] > 0 else "")
                        )
                        _sq_col3.markdown(
                            f"**Total: {_sq_r['total']:,.2f} €**"
                            + (f"  ·  {_sq_r['tt_days']}d" if _sq_r.get('tt_days') else "")
                        )
                        if _sq_col4.button(
                            f"✅ Usar {_sq_r['total']:,.2f} €",
                            key=f"use_freight_{_sq_r['carrier']}_cot",
                            type="primary",
                            use_container_width=True,
                        ):
                            st.session_state["freight_from_sim"] = float(_sq_r["total"])
                            st.session_state.pop("sim_quotes_cot", None)
                            st.rerun()

    st.divider()

    # ── 3. Produtos ───────────────────────────────────────────────────────────
    st.subheader("3. Produtos a Cotar")

    if "product_basket" not in st.session_state:
        st.session_state["product_basket"] = {}
    if "so_manual" not in st.session_state:
        st.session_state["so_manual"] = {}
    if "margin_override" not in st.session_state:
        st.session_state["margin_override"] = {}

    col_sa, col_sb = st.columns([2,2])
    with col_sa:
        search_mode = st.radio("Pesquisar por", ["SKU ID","EAN"], horizontal=True)
    with col_sb:
        margin_mode = st.radio("Margem por", ["Percentagem (%)","Valor (€/un.)"], horizontal=True)

    col_a, col_b = st.columns([3,1])
    with col_a:
        ph = "Ex: 2062910, 2062944" if search_mode=="SKU ID" else "Ex: 5908099018610, 8806090268380"
        lbl = "SKUs (separados por vírgula) *" if search_mode=="SKU ID" else "EANs (separados por vírgula) *"
        ids_raw = st.text_input(lbl, placeholder=ph)
    with col_b:
        if margin_mode == "Percentagem (%)":
            margin_val = st.number_input("Margem %", min_value=0.0, max_value=200.0, value=5.0, step=0.5)
        else:
            margin_val = st.number_input("Margem €/un.", min_value=0.0, max_value=9999.0, value=10.0, step=1.0)

    btn_add, btn_manual, btn_clear = st.columns([2, 2, 4])
    add_clicked    = btn_add.button("➕  Adicionar ao Cesto", type="primary")
    manual_clicked = btn_manual.button("✏️  Produto Manual")

    if add_clicked and ids_raw.strip():
        import re
        id_list = [s.strip() for s in re.split(r'[,\s]+', ids_raw.strip()) if s.strip()]
        with st.spinner(f"A consultar {len(id_list)} produto(s)..."):
            index = load_index()
            if search_mode == "SKU ID":
                results = {s: index.get(s) for s in id_list}
            else:
                ean_idx = {v.get("ean","").strip(): v for v in index.values() if v.get("ean")}
                results  = {e: ean_idx.get(e) for e in id_list}

        found     = {k: v for k,v in results.items() if v}
        not_found = [k for k,v in results.items() if not v]

        if not_found:
            st.warning(f"Não encontrados: **{', '.join(not_found)}**")
        if found:
            # Normalizar por SKU ID e adicionar ao cesto
            for ref, d in found.items():
                sku_id = d.get("sku_id", ref)
                st.session_state["product_basket"][sku_id] = d
                if sku_id not in st.session_state["so_manual"]:
                    st.session_state["so_manual"][sku_id] = 0.0
            st.session_state["margin_mode"]       = margin_mode
            st.session_state["margin_val"]        = margin_val
            st.session_state["selected_incoterm"] = selected_incoterm
            st.session_state["payment_conditions"] = payment_conditions
            st.success(f"✅ {len(found)} produto(s) adicionado(s) ao cesto.")

    # ── Produto manual ────────────────────────────────────────────────────────
    if "show_manual_form" not in st.session_state:
        st.session_state["show_manual_form"] = False
    if manual_clicked:
        st.session_state["show_manual_form"] = not st.session_state["show_manual_form"]

    if st.session_state.get("show_manual_form"):
        with st.container(border=True):
            st.caption("✏️ Adicionar produto manualmente")
            m1, m2, m3, m4 = st.columns([1.5, 2, 3, 1.5])
            man_sku   = m1.text_input("SKU / Ref.", placeholder="Ex: REF-001", key="man_sku")
            man_ean   = m2.text_input("EAN", placeholder="Ex: 1234567890123", key="man_ean")
            man_name  = m3.text_input("Descrição *", placeholder="Ex: Samsung TV 55\" QLED", key="man_name")
            man_brand = m4.text_input("Marca", placeholder="Ex: Samsung", key="man_brand")
            m5, m6, m7 = st.columns([1.5, 1.5, 5])
            man_cost  = m5.number_input("Custo (€) *", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="man_cost")
            man_pvp   = m6.number_input("Preço Cliente (€)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="man_pvp",
                                         help="Opcional — deixar 0 para usar margem global")
            if st.button("➕ Adicionar produto manual", type="primary"):
                if man_name and man_cost > 0:
                    _ref = man_sku.strip() or f"MANUAL-{len(st.session_state['product_basket'])+1:03d}"
                    st.session_state["product_basket"][_ref] = {
                        "sku_id":  _ref,
                        "ean":     man_ean.strip() or "N/A",
                        "name":    man_name.strip(),
                        "brand":   man_brand.strip() or "—",
                        "ufc_raw": man_cost,
                        "pvp_pt":  None,
                        "eis_total": 0.0,
                        "eis_da":  0,
                        "sell_in": None,
                        "sell_out": 0.0,
                        "_manual": True,
                        "_pvp_override": man_pvp if man_pvp > 0 else None,
                    }
                    st.session_state["so_manual"][_ref] = 0.0
                    st.session_state["margin_mode"]  = margin_mode
                    st.session_state["margin_val"]   = margin_val
                    st.session_state["show_manual_form"] = False
                    st.success(f"✅ Produto manual **{_ref}** adicionado.")
                    st.rerun()
                else:
                    st.error("Preenche pelo menos Descrição e Custo.")

    # ── Cesto de produtos ─────────────────────────────────────────────────────
    basket = st.session_state.get("product_basket", {})

    if basket:
        st.markdown("---")
        s_margin_mode = st.session_state.get("margin_mode", "Percentagem (%)")
        s_margin_val  = st.session_state.get("margin_val", 5.0)

        # ── Margem Mínima (threshold configurável) ────────────────────────────
        _mm_col1, _mm_col2 = st.columns([2, 6])
        min_margin_pct = _mm_col1.number_input(
            "🚨 Margem Mínima (%)",
            min_value=0.0, max_value=50.0,
            value=st.session_state.get("min_margin_pct", MIN_MARGIN_DEFAULT),
            step=0.5, format="%.1f",
            help="Alerta visual por linha se a margem calculada ficar abaixo deste valor.",
            key="min_margin_pct_input",
        )
        st.session_state["min_margin_pct"] = min_margin_pct

        # Cabeçalho
        _unit = "%" if s_margin_mode == "Percentagem (%)" else "€"
        hcols = st.columns([0.8, 1.2, 1.5, 2.8, 1.4, 1.4, 1.4, 1.2, 1.6, 1.4, 1.4, 0.5])
        for col, lbl in zip(hcols, ["Qty","SKU","EAN","Produto",
                                     "FC Simulador","SO Negoc. (€)","FC Final",
                                     f"Margem ({_unit})","Preço Cliente","EIS DA","Sell-In","✕"]):
            col.caption(lbl)
        st.markdown("---")

        qty_map = {}
        any_nd  = False

        for sku, d in list(basket.items()):
            ufc_raw   = d.get("ufc_raw")
            eis_total = d.get("eis_total") or 0.0
            sell_out  = d.get("sell_out")  or 0.0
            eis_da    = d.get("eis_da") or 0
            sell_in   = d.get("sell_in")
            ean       = d.get("ean") or "—"

            cols = st.columns([0.8, 1.2, 1.5, 2.8, 1.4, 1.4, 1.4, 1.2, 1.6, 1.4, 1.4, 0.5])

            if f"qty_{sku}" not in st.session_state:
                st.session_state[f"qty_{sku}"] = 1
            qty_map[sku] = cols[0].number_input("", min_value=1, step=1,
                                                key=f"qty_{sku}", label_visibility="collapsed")

            cols[1].markdown(f"**`{sku}`**")
            cols[2].markdown(f"`{ean}`")
            cols[3].markdown(f"{d.get('brand','')[:12]} · {d.get('name','')[:35]}")

            # FC_sim depende do destino (vat_rate vem da secção 2)
            # Para exportação, deduz EIS do PCL (taxa não aplicável fora de PT)
            _eis_deduct = (eis_total or eis_da or 0.0)   # fallback para eis_da se eis_total=0
            if ufc_raw is not None:
                if vat_rate > 0:   # Portugal — EIS incluído no PCL, sem dedução
                    fc_sim = round(ufc_raw + sell_out, 4)
                else:              # Exportação — EIS deduzido do PCL
                    fc_sim = round(ufc_raw - _eis_deduct + sell_out, 4)
                cols[4].markdown(f"**{fmt4(fc_sim)}**")
            else:
                fc_sim = None
                cols[4].markdown("⚠️ N/D")
                any_nd = True

            # SO negociação — campo manual por SKU
            so_neg = cols[5].number_input("", min_value=0.0, value=st.session_state["so_manual"].get(sku, 0.0),
                                          step=0.5, format="%.2f", key=f"so_{sku}",
                                          label_visibility="collapsed",
                                          help="Apoio Sell-Out a negociar com o fabricante (€/un.)")
            st.session_state["so_manual"][sku] = so_neg

            # FC Final = FC_sim - SO_negociação
            fc_final = round(fc_sim - so_neg, 4) if fc_sim is not None else None

            # Margem por linha — usa global como default, editável individualmente
            _m_default = st.session_state["margin_override"].get(sku, s_margin_val)
            _m_max = 200.0 if s_margin_mode == "Percentagem (%)" else 9999.0
            _m_line = cols[7].number_input("", min_value=0.0, max_value=_m_max,
                                           value=float(_m_default), step=0.5, format="%.1f",
                                           key=f"mg_{sku}", label_visibility="collapsed",
                                           help="Margem para este SKU (sobrepõe o global)")
            st.session_state["margin_override"][sku] = _m_line

            pvp = calc_pvp(fc_final, s_margin_mode, _m_line)

            # Calcular margem real da linha para alerta visual
            _line_margin_pct = margin_pct(fc_final, pvp) if (fc_final and pvp) else 0.0
            _below_min = fc_final is not None and pvp is not None and _line_margin_pct < min_margin_pct

            cols[6].markdown(f"**{fmt4(fc_final)}**" if fc_final else "—")

            # Preço Cliente — cor vermelha se abaixo da margem mínima
            if pvp:
                if _below_min:
                    cols[8].markdown(
                        f'<span style="color:#CC0000;font-weight:700;">{fmt4(pvp)}</span>'
                        f' <span title="Margem {_line_margin_pct:.1f}% abaixo do mínimo {min_margin_pct:.1f}%">⚠️</span>',
                        unsafe_allow_html=True
                    )
                else:
                    cols[8].markdown(
                        f'<span style="color:#007700;font-weight:700;">{fmt4(pvp)}</span>',
                        unsafe_allow_html=True
                    )
            else:
                cols[8].markdown("—")

            # EIS: mostrar dedução se exportação, ou aviso se Portugal
            if eis_da > 0:
                if vat_rate == 0:
                    cols[9].markdown(f"✅ -{fmt4(_eis_deduct)}")   # deduzido do PCL
                else:
                    cols[9].markdown(f"⚠️ {fmt4(eis_da)}")         # incluído (PT)
            else:
                cols[9].markdown("—")
            cols[10].markdown(f"{'✅ ' if sell_in else ''}{fmt4(sell_in) if sell_in else '—'}")

            if cols[11].button("✕", key=f"rm_{sku}", help="Remover produto"):
                del st.session_state["product_basket"][sku]
                st.session_state["so_manual"].pop(sku, None)
                st.session_state["margin_override"].pop(sku, None)
                st.rerun()

            # ── Histórico de preços negociados para este SKU ──────────────────
            with st.expander(f"📋 Histórico de deals — {sku}", expanded=False):
                _hist = get_sku_price_history(sku, limit=8)
                if not _hist:
                    st.caption("Sem deals anteriores com este SKU.")
                else:
                    import pandas as _pd_hist
                    _hist_rows = []
                    for _h in _hist:
                        _company = _h.get("company") or ""
                        _client  = _h.get("client") or "—"
                        _label   = f"{_company} / {_client}" if _company else _client
                        _hist_rows.append({
                            "Deal ID":    _h.get("deal_id","—"),
                            "Data":       (_h.get("created_at") or "")[:10],
                            "Cliente":    _label,
                            "País":       _h.get("country","—"),
                            "Status":     _h.get("status","—"),
                            "Margem %":   _h.get('margin_pct') or "—",
                            "Valor (€)":  f"{float(_h.get('proposed_value') or 0):,.2f}",
                        })
                    st.dataframe(
                        _pd_hist.DataFrame(_hist_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

        if any_nd:
            st.markdown('<div class="warn-box">⚠️ Alguns SKUs sem FC disponível. '
                        'Verifica o simulador.</div>', unsafe_allow_html=True)

        # ── 4. Resumo financeiro ──────────────────────────────────────────────
        st.markdown("---")
        so_manual_map = st.session_state.get("so_manual", {})

        def _fc_sim_for(d):
            raw = d.get("ufc_raw") or 0
            eis = (d.get("eis_total") or d.get("eis_da") or 0)  # fallback eis_da
            so  = d.get("sell_out") or 0
            return round(raw + so, 4) if vat_rate > 0 else round(raw - eis + so, 4)

        _mg_override = st.session_state.get("margin_override", {})
        total_fc_final = sum(
            round(_fc_sim_for(basket[s]) - so_manual_map.get(s, 0), 4) * qty_map[s]
            for s in basket
        )
        total_pvp = sum(
            (calc_pvp(round(_fc_sim_for(basket[s]) - so_manual_map.get(s, 0), 4),
                      s_margin_mode, _mg_override.get(s, s_margin_val)) or 0) * qty_map[s]
            for s in basket
        )
        overall_margin = margin_pct(total_fc_final, total_pvp) if total_pvp else 0


        vat_amount   = round((total_pvp + freight_cost) * vat_rate, 2)
        total_client = round(total_pvp + freight_cost + vat_amount, 2)

        mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
        mc1.metric("Total FC Final", f"{total_fc_final:,.2f} €")
        mc2.metric("Produtos (s/ frete)", f"{total_pvp:,.2f} €")
        mc3.metric("Frete", f"{freight_cost:,.2f} €")
        mc4.metric(f"IVA ({int(vat_rate*100)}%)", f"{vat_amount:,.2f} €")
        mc5.metric("Total a Pagar", f"{total_client:,.2f} €")
        _margin_delta = round(overall_margin - min_margin_pct, 1)
        mc6.metric("Margem %", f"{overall_margin:.1f}%",
                   delta=f"{_margin_delta:+.1f}pp vs mín.",
                   delta_color="normal" if overall_margin >= min_margin_pct else "inverse")

        if overall_margin < min_margin_pct:
            st.error(
                f"🚨 **Margem global ({overall_margin:.1f}%) abaixo do mínimo definido ({min_margin_pct:.1f}%).** "
                f"Revê os preços ou negocia mais apoio SO com o fornecedor."
            )

        s_incoterm = st.session_state.get("selected_incoterm", INCOTERMS_LIST[0])
        s_payment  = st.session_state.get("payment_conditions", PAYMENT_CONDITIONS_DEFAULT)
        st.caption(f"📋 **Incoterm:** {s_incoterm}  ·  💳 **Pagamento:** {s_payment}  ·  🧾 **{vat_sel}**")

        # Botão limpar cesto
        if st.button("🗑️  Limpar cesto", key="clear_basket"):
            _clear_state()
            st.rerun()

        st.markdown("---")
        st.subheader("4. Criar Deal")
        b1, b2 = st.columns(2)
        criar_deal  = b1.button("💾  Criar Deal (sem email)", use_container_width=True)
        criar_email = b2.button("✉️  Criar Deal + Gerar Email  ›  Aprovação",
                                type="primary", use_container_width=True)

        if (criar_deal or criar_email) and client and email:
            skus_data = {}
            for sku in basket:
                so_neg    = so_manual_map.get(sku, 0.0)
                fc_sim    = _fc_sim_for(basket[sku])
                fc_final  = round(fc_sim - so_neg, 4)
                _m_sku    = _mg_override.get(sku, s_margin_val)
                pvp_unit  = calc_pvp(fc_final, s_margin_mode, _m_sku)
                skus_data[sku] = {
                    "qty":      qty_map[sku],
                    "data":     basket[sku],
                    "so_neg":   so_neg,
                    "fc_final": fc_final,
                    "pvp":      pvp_unit,
                    "margin":   _m_sku,
                }

            with st.spinner("A criar deal..."):
                deal_id = add_deal(client=client, country=country, email=email,
                                   language=language, skus_data=skus_data, notes=notes,
                                   margin_pct=round(overall_margin, 2),
                                   pvp_total=round(total_client, 2),
                                   vat_rate=vat_rate,
                                   incoterm=s_incoterm,
                                   payment_conditions=s_payment,
                                   freight_cost=freight_cost,
                                   availability=availability,
                                   salesperson_email=_cu.get("email",""),
                                   company=company)

            # Auto-registar/enriquecer cliente no CRM
            try:
                _, _is_new_client = upsert_from_deal(
                    contact_name = client,
                    company_name = company,
                    email        = email,
                    country      = country,
                    incoterm     = s_incoterm,
                    payment      = s_payment,
                )
            except Exception:
                _is_new_client = False

            if criar_deal:
                _msg = f"✅ Deal **{deal_id}** criado."
                if _is_new_client:
                    _msg += " Cliente adicionado ao CRM."
                st.success(_msg)
                _clear_state()
                st.rerun()

            elif criar_email:
                with st.spinner("A gerar email com Claude AI..."):
                    try:
                        html_body, pvp_calc, margin_calc = generate_proposal(
                            client_name=client, client_email=email, country=country,
                            language=language, skus_data=skus_data, deal_id=deal_id,
                            margin_mode=s_margin_mode, margin_val=s_margin_val,
                            notes=notes, incoterm=s_incoterm, payment_conditions=s_payment,
                            freight_cost=freight_cost, vat_rate=vat_rate,
                            availability=availability,
                            company=company,
                        )
                        st.session_state["pending_email"] = {
                            "html_body":    html_body,
                            "deal_id":      deal_id,
                            "pvp_total":    pvp_calc,
                            "margin_calc":  margin_calc,
                            "client_email": email,
                            "client_name":  client,
                            "company":      company,
                            "language":     language,
                        }
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao gerar email: {e}")
                        import traceback; st.code(traceback.format_exc())

        elif (criar_deal or criar_email) and not (client and email):
            st.error("⚠️ Preenche o **Nome do cliente** e **Email** antes de continuar.")


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA — DASHBOARD EXECUTIVO
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊  Dashboard":
    import pandas as pd
    st.title("📊 Dashboard Executivo — BoxMovers")

    # Filtros
    _db_c1, _db_c2, _db_c3 = st.columns([2, 2, 4])
    _current_year = datetime.now().year
    _db_year = _db_c1.selectbox(
        "Ano", [None, _current_year, _current_year - 1],
        format_func=lambda x: "Todos os anos" if x is None else str(x),
        key="db_year",
    )
    _db_sp_filter = None
    if _role in OWN_DATA_ONLY:
        _db_sp_filter = _cu.get("email")
    elif _role == "comercial_interno":
        _db_own = _db_c2.checkbox("Apenas os meus deals", value=False, key="db_own")
        if _db_own:
            _db_sp_filter = _cu.get("email")

    if st.button("🔄 Actualizar Dashboard", key="btn_db_refresh", type="primary"):
        st.session_state.pop("exec_dash", None)

    if "exec_dash" not in st.session_state:
        with st.spinner("A calcular..."):
            st.session_state["exec_dash"] = get_executive_dashboard_data(
                year=_db_year,
                salesperson_filter=_db_sp_filter,
            )

    _dash = st.session_state.get("exec_dash", {})
    if not _dash:
        st.info("Sem dados disponíveis.")
        st.stop()

    _rev        = _dash.get("total_revenue", 0)
    _pipe       = _dash.get("total_pipeline", 0)
    _margin     = _dash.get("avg_margin", 0)
    _gm_val     = _dash.get("gross_margin_value", 0)
    _our_cut    = _dash.get("our_cut", 0)
    _ebitda_est = _our_cut - BP_FIXED_COSTS
    _win_rate   = _dash.get("win_rate", 0)
    _take_rate  = round(_our_cut / _rev * 100, 2) if _rev > 0 else 0.0

    # ── Tabs ──────────────────────────────────────────────────────────────
    _d_tab1, _d_tab2, _d_tab3 = st.tabs([
        "📈 KPIs & P&L", "👥 Por Comercial", "📅 Evolução Mensal"
    ])

    # ════════════════════════════════════════════════════════════════════
    with _d_tab1:
        st.subheader("Indicadores-Chave de Desempenho")

        # Row 1: Revenue KPIs
        _k1, _k2, _k3, _k4 = st.columns(4)
        _rev_pct    = round(_rev / BP_TARGET_REVENUE * 100, 1) if BP_TARGET_REVENUE else 0
        _be_pct     = round(_rev / BP_BREAK_EVEN * 100, 1)     if BP_BREAK_EVEN else 0
        _ebitda_pct = round(_ebitda_est / BP_TARGET_EBITDA * 100, 1) if BP_TARGET_EBITDA and _ebitda_est > 0 else 0

        _k1.metric(
            "💶 Faturação Realizada",
            f"{_rev:,.0f} €",
            delta=f"{_rev_pct:.1f}% do alvo ({BP_TARGET_REVENUE/1e6:.0f}M €)",
        )
        _k2.metric(
            "📦 Pipeline Ativo",
            f"{_pipe:,.0f} €",
            delta=f"Potencial: {_rev + _pipe:,.0f} €",
        )
        _k3.metric(
            "🎯 Taxa de Sucesso",
            f"{_win_rate:.1f}%",
            delta=f"{_dash.get('won_deals',0)} ganhos · {_dash.get('lost_deals',0)} perdidos",
        )
        _k4.metric(
            "📊 Margem Média",
            f"{_margin:.1f}%",
        )

        # Break-even progress bar
        st.divider()
        st.subheader("🏁 Progresso vs. Break-Even")
        _be_progress = min(_rev / BP_BREAK_EVEN, 1.0) if BP_BREAK_EVEN else 0
        st.progress(_be_progress, text=f"Break-even: {BP_BREAK_EVEN/1e6:.1f}M €  ·  Alcançado: {_be_pct:.1f}%")
        _target_progress = min(_rev / BP_TARGET_REVENUE, 1.0) if BP_TARGET_REVENUE else 0
        st.progress(_target_progress, text=f"Alvo: {BP_TARGET_REVENUE/1e6:.0f}M €  ·  Alcançado: {_rev_pct:.1f}%")

        st.divider()
        st.subheader("💰 P&L Simplificado")

        _pl1, _pl2 = st.columns([2, 1])
        with _pl1:
            _pl_rows = [
                {"Item": "📦 Faturação Total",       "Valor (€)": f"{_rev:>15,.2f}",    "Notas": f"Cenário alvo: {BP_TARGET_REVENUE/1e6:.0f}M €"},
                {"Item": "📉 Margem Bruta Estimada", "Valor (€)": f"{_gm_val:>15,.2f}", "Notas": f"{_margin:.1f}% médio"},
                {"Item": "🎯 Proveito BoxMovers (30%)", "Valor (€)": f"{_our_cut:>15,.2f}", "Notas": f"Take-rate: {_take_rate:.2f}% (alvo {BP_TAKE_RATE*100:.2f}%)"},
                {"Item": "➖ Custos Fixos Anuais",   "Valor (€)": f"-{BP_FIXED_COSTS:>14,.2f}", "Notas": "2 colabs + 2 contractors"},
                {"Item": "═══════════════════",       "Valor (€)": "═══════════════", "Notas": ""},
                {"Item": "📊 EBITDA Estimado",        "Valor (€)": f"{_ebitda_est:>15,.2f}", "Notas": f"Alvo: {BP_TARGET_EBITDA/1e3:.0f}k €"},
            ]
            st.dataframe(pd.DataFrame(_pl_rows), use_container_width=True, hide_index=True)

        with _pl2:
            st.metric("Take-rate real", f"{_take_rate:.2f}%",
                      delta=f"Alvo: {BP_TAKE_RATE*100:.2f}%",
                      delta_color="normal" if _take_rate >= BP_TAKE_RATE*100 else "inverse")
            st.metric("EBITDA estimado", f"{_ebitda_est:,.0f} €",
                      delta=f"Gap vs. alvo: {_ebitda_est - BP_TARGET_EBITDA:+,.0f} €",
                      delta_color="normal" if _ebitda_est >= BP_TARGET_EBITDA else "inverse")
            st.metric("Break-even", "✅ Atingido" if _rev >= BP_BREAK_EVEN else "❌ Não atingido",
                      delta=f"{(_rev - BP_BREAK_EVEN):+,.0f} €",
                      delta_color="normal" if _rev >= BP_BREAK_EVEN else "inverse")

        st.divider()
        st.subheader("📋 Distribuição por Status")
        _status_counts = _dash.get("status_counts", {})
        if _status_counts:
            _sc_rows = []
            for _s in STATUSES:
                _cnt = _status_counts.get(_s, 0)
                if _cnt > 0:
                    _sc_rows.append({"Status": f"{STATUS_EMOJI.get(_s,'')} {_s}", "Deals": _cnt})
            if _sc_rows:
                _sc_df = pd.DataFrame(_sc_rows).set_index("Status")
                st.bar_chart(_sc_df)

    # ════════════════════════════════════════════════════════════════════
    with _d_tab2:
        st.subheader("👥 Performance por Comercial")
        _sp_list = _dash.get("by_salesperson", [])
        if not _sp_list:
            st.info("Sem dados por comercial.")
        else:
            # KPIs globais (summed)
            _sp_kpi1, _sp_kpi2, _sp_kpi3 = st.columns(3)
            _sp_kpi1.metric("Comerciais activos", len([s for s in _sp_list if s["revenue"] > 0 or s["pipeline"] > 0]))
            _sp_kpi2.metric("Total Deals Ganhos", sum(s["won"] for s in _sp_list))
            _sp_kpi3.metric("Total Deals Perdidos", sum(s["lost"] for s in _sp_list))

            st.divider()

            _sp_df_rows = []
            for _sp in _sp_list:
                _sp_df_rows.append({
                    "Comercial":       _sp["email"],
                    "Faturação (€)":   f"{_sp['revenue']:,.0f}",
                    "Pipeline (€)":    f"{_sp['pipeline']:,.0f}",
                    "Deals Ganhos":    _sp["won"],
                    "Deals Perdidos":  _sp["lost"],
                    "Activos":         _sp["active"],
                    "Margem Média %":  f"{_sp['avg_margin']:.1f}%",
                    "Win Rate %":      f"{_sp['win_rate']:.1f}%",
                })
            st.dataframe(pd.DataFrame(_sp_df_rows), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("📊 Faturação por Comercial")
            _sp_chart_rows = [
                {"Comercial": s["email"].split("@")[0], "Faturação": s["revenue"]}
                for s in _sp_list if s["revenue"] > 0
            ]
            if _sp_chart_rows:
                _sp_chart = pd.DataFrame(_sp_chart_rows).set_index("Comercial")
                st.bar_chart(_sp_chart)
            else:
                st.info("Sem faturação registada para gerar o gráfico.")

    # ════════════════════════════════════════════════════════════════════
    with _d_tab3:
        st.subheader("📅 Evolução Mensal da Faturação")
        _monthly = _dash.get("monthly_revenue", {})
        if not _monthly:
            st.info("Sem dados mensais disponíveis.  \n_Nota: os meses são calculados pela data de criação dos deals._")
        else:
            _m_df = pd.DataFrame([
                {"Mês": k, "Faturação (€)": v}
                for k, v in _monthly.items()
            ]).set_index("Mês")
            st.bar_chart(_m_df)

            # Cumulative
            _cum_total = 0.0
            _cum_rows  = []
            for _mk, _mv in _monthly.items():
                _cum_total += _mv
                _cum_rows.append({
                    "Mês":               _mk,
                    "Mensal (€)":        f"{_mv:,.2f}",
                    "Acumulado (€)":     f"{_cum_total:,.2f}",
                    "% do Alvo Anual":   f"{_cum_total / BP_TARGET_REVENUE * 100:.1f}%",
                })
            st.dataframe(pd.DataFrame(_cum_rows), use_container_width=True, hide_index=True)

            # Annualized projection
            _months_with_data = len(_monthly)
            if _months_with_data > 0:
                _annualized = round(_cum_total / _months_with_data * 12, 0)
                st.divider()
                _pr1, _pr2, _pr3 = st.columns(3)
                _pr1.metric("📈 Projecção Anualizada", f"{_annualized:,.0f} €",
                            delta=f"vs alvo {BP_TARGET_REVENUE/1e6:.0f}M: {_annualized-BP_TARGET_REVENUE:+,.0f} €",
                            delta_color="normal" if _annualized >= BP_TARGET_REVENUE else "inverse")
                _pr2.metric("🎯 vs Break-Even", f"{_annualized / BP_BREAK_EVEN * 100:.1f}%",
                            delta="✅ Acima" if _annualized >= BP_BREAK_EVEN else "❌ Abaixo")
                _pr3.metric("📊 vs Cenário Base", f"{_annualized / BP_SCENARIO_BASE * 100:.1f}%",
                            delta=f"Base: {BP_SCENARIO_BASE/1e6:.0f}M €")

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 2 — DEALS EM CURSO (inclui follow-up)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋  Deals em Curso":
    import pandas as pd
    st.title("📋 Pipeline de Deals")

    # ── Tabs: Lista / Pipeline ────────────────────────────────────────────────
    _dp_tab1, _dp_tab2 = st.tabs(["📋 Lista de Deals", "📊 Dashboard Pipeline"])

    with _dp_tab2:
        _sp_filter_dash = _cu.get("email") if _role in OWN_DATA_ONLY else None
        _pipe_stats = get_pipeline_stats(salesperson_filter=_sp_filter_dash)
        _by_st      = _pipe_stats.get("by_status", {})
        _stale      = _pipe_stats.get("stale", [])

        # ── Alertas de risco ──────────────────────────────────────────────
        if _stale:
            st.warning(f"⚠️ **{len(_stale)} deal(s) sem actividade há ≥ {DEAL_STALE_DAYS} dias** — risco de perda!")
            with st.expander(f"🔴 Ver deals em risco ({len(_stale)})", expanded=False):
                _stale_sorted = sorted(_stale, key=lambda x: x["days"], reverse=True)
                for _sr in _stale_sorted:
                    _sr_col1, _sr_col2, _sr_col3, _sr_col4 = st.columns([2, 2, 1, 1])
                    _sr_col1.markdown(f"**{_sr['deal_id']}** — {_sr['client']}")
                    _sr_col2.markdown(f"{STATUS_EMOJI.get(_sr['status'], '')} {_sr['status']}")
                    _sr_col3.markdown(f"🕐 **{_sr['days']}** dias")
                    _sr_col4.markdown(f"{fmt2(_sr['value'])}")
        else:
            st.success("✅ Sem deals em risco de inactividade.")

        st.divider()

        # ── Métricas por grupo ─────────────────────────────────────────────
        _active_count  = sum(_by_st.get(s, {}).get("count", 0) for s in PIPELINE_ACTIVE_STATUSES)
        _active_val    = sum(_by_st.get(s, {}).get("value", 0) for s in PIPELINE_ACTIVE_STATUSES)
        _order_count   = sum(_by_st.get(s, {}).get("count", 0) for s in PIPELINE_ORDER_STATUSES)
        _order_val     = sum(_by_st.get(s, {}).get("value", 0) for s in PIPELINE_ORDER_STATUSES)
        _closed_count  = _by_st.get("Faturado", {}).get("count", 0)
        _closed_val    = _by_st.get("Faturado", {}).get("value", 0)
        _lost_count    = _by_st.get("Perdido", {}).get("count", 0)

        st.subheader("Resumo do Pipeline")
        _pm1, _pm2, _pm3, _pm4 = st.columns(4)
        _pm1.metric("💼 Negociação Activa", f"{_active_count} deals", f"{_active_val:,.0f} €")
        _pm2.metric("📦 Em Processamento", f"{_order_count} deals", f"{_order_val:,.0f} €")
        _pm3.metric("🧾 Faturado", f"{_closed_count} deals", f"{_closed_val:,.0f} €")
        _pm4.metric("❌ Perdidos", f"{_lost_count} deals")

        st.divider()
        st.subheader("Detalhes por Status")

        _all_statuses_ordered = STATUSES
        _pipe_rows = []
        for _ps in _all_statuses_ordered:
            _psi = _by_st.get(_ps, {})
            if _psi.get("count", 0) > 0:
                _pipe_rows.append({
                    "Status":    f"{STATUS_EMOJI.get(_ps,'')} {_ps}",
                    "Deals":     _psi["count"],
                    "Valor (€)": f"{_psi['value']:,.2f} €",
                })
        if _pipe_rows:
            st.dataframe(pd.DataFrame(_pipe_rows), use_container_width=True, hide_index=True)
        else:
            st.info("Sem dados de pipeline.")

    with _dp_tab1:
        cf1, cf2, _ = st.columns([2,2,4])
        status_filter = cf1.selectbox("Filtrar status", ["Todos"]+STATUSES)
        search_client = cf2.text_input("Pesquisar cliente", placeholder="Nome...")

        # Contractors vêem apenas os seus próprios deals
        _sp_filter = _cu.get("email") if _role in OWN_DATA_ONLY else None
        deals = list_deals(None if status_filter=="Todos" else status_filter,
                           salesperson_filter=_sp_filter)
        if search_client:
            deals = [d for d in deals if search_client.lower() in str(d.get("Cliente","")).lower()]

        st.caption(f"{len(deals)} deal(s)")
        if not deals:
            st.info("Sem deals para os filtros selecionados.")
        else:
            # ── Apagar múltiplos deals ─────────────────────────────────────────
            if _role in CAN_EDIT_DEALS:
                with st.expander("🗑️ Apagar múltiplos deals"):
                    st.caption("Seleciona os deals que pretendes eliminar e confirma no final.")
                    _bulk_selected = []
                    for _ds in reversed(deals):
                        _bdid   = str(_ds.get("Deal ID",""))
                        _bcl    = str(_ds.get("Cliente",""))
                        _bst    = str(_ds.get("Status",""))
                        _bval   = _ds.get("Valor Proposto (€)","")
                        _blabel = (f"{_bdid}  ·  {_bcl}  ·  "
                                   f"{STATUS_EMOJI.get(_bst,'')} {_bst}  ·  {fmt2(_bval)} €")
                        if st.checkbox(_blabel, key=f"bulk_chk_{_bdid}"):
                            _bulk_selected.append(_bdid)

                    if _bulk_selected:
                        st.warning(
                            f"**{len(_bulk_selected)} deal(s) selecionado(s):** "
                            + ", ".join(_bulk_selected)
                        )
                        if not st.session_state.get("bulk_del_confirm"):
                            if st.button(
                                f"🗑️ Apagar {len(_bulk_selected)} deal(s) selecionado(s)",
                                key="bulk_del_btn", type="secondary",
                            ):
                                st.session_state["bulk_del_confirm"] = True
                                st.rerun()
                        else:
                            st.error(
                                f"⚠️ Esta ação é **irreversível**. "
                                f"Confirmas o apagamento de **{len(_bulk_selected)} deal(s)**?"
                            )
                            _bc1, _bc2 = st.columns(2)
                            if _bc1.button("✅ Sim, apagar todos", key="bulk_del_yes", type="primary"):
                                _errs = [bid for bid in _bulk_selected if not delete_deal(bid)]
                                st.session_state["bulk_del_confirm"] = False
                                for bid in _bulk_selected:
                                    st.session_state.pop(f"bulk_chk_{bid}", None)
                                if _errs:
                                    st.error(f"Erro ao apagar: {', '.join(_errs)}")
                                else:
                                    st.success(f"✅ {len(_bulk_selected)} deal(s) apagado(s) com sucesso.")
                                st.rerun()
                            if _bc2.button("❌ Cancelar", key="bulk_del_no"):
                                st.session_state["bulk_del_confirm"] = False
                                st.rerun()
                    else:
                        st.info("Seleciona pelo menos um deal para apagar.")

            for deal_summary in reversed(deals):
                did    = str(deal_summary.get("Deal ID",""))
                cl     = str(deal_summary.get("Cliente",""))
                cntry  = str(deal_summary.get("País",""))
                status = str(deal_summary.get("Status",""))
                value  = deal_summary.get("Valor Proposto (€)","")
                upd    = str(deal_summary.get("Data Último Update",""))[:16]

                with st.expander(f"{did}  ·  {cl} ({cntry})  ·  "
                                 f"{STATUS_EMOJI.get(status,'')} {status}  ·  {fmt2(value)} €"):

                    # Carregar detalhe completo
                    deal = get_deal(did)
                    if not deal:
                        deal = deal_summary

                    # ── Cabeçalho ──────────────────────────────────────────────
                    h1, h2, h3, h4, h5 = st.columns(5)
                    h1.markdown(f"**Cliente**  \n{cl}")
                    h2.markdown(f"**País**  \n{cntry}")
                    h3.markdown(f"**Língua**  \n{deal.get('Língua','—')}")
                    h4.markdown(f"**Margem**  \n{deal.get('Margem %','—')}")
                    h5.markdown(f"**Última atualização**  \n{upd}")

                    # ── Condições comerciais ────────────────────────────────────
                    st.markdown("**Condições Comerciais**")
                    cc1, cc2, cc3, cc4, cc5 = st.columns(5)
                    cc1.markdown(f"**Incoterm**  \n{deal.get('Incoterm','—')}")
                    cc2.markdown(f"**Pagamento**  \n{deal.get('Pagamento','—')}")
                    cc3.markdown(f"**IVA**  \n{deal.get('IVA','—')}")
                    cc4.markdown(f"**Frete**  \n{fmt2(deal.get('Frete (€)',0))} €")
                    cc5.markdown(f"**Availability / ETA**  \n{deal.get('Availability / ETA','—')}")

                    # ── Tabela de produtos ──────────────────────────────────────
                    st.markdown("**Produtos Negociados**")
                    prods_rows = deal_products_table(deal)
                    if prods_rows:
                        df = pd.DataFrame(prods_rows)
                        # Totais
                        total_row = {c: "" for c in df.columns}
                        total_row["Produto"] = "**TOTAL**"
                        total_row["Qty"]     = int(df["Qty"].sum())
                        total_row["Total (€)"] = round(df["Total (€)"].sum(), 2)
                        df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.caption(f"Produtos: {str(deal_summary.get('Produtos',''))}")

                    # ── Editar tabela de preços ────────────────────────────────
                    if _role in CAN_EDIT_DEALS:
                        st.markdown("---")
                        _edit_key = f"edit_prices_{did}"
                        if st.button("✏️ Editar Tabela de Preços", key=f"btn_edit_{did}"):
                            st.session_state[_edit_key] = not st.session_state.get(_edit_key, False)

                        if st.session_state.get(_edit_key):
                            _skus_edit = dict(deal.get("_skus_detail") or {})
                            if not _skus_edit:
                                st.warning("Sem dados de produtos para editar.")
                            else:
                                with st.container(border=True):
                                    st.caption("✏️ Editar preços — altera Qty e/ou Margem % por linha · Preço Cliente é calculado automaticamente")
                                    _vat_str_e  = str(deal.get("IVA", ""))
                                    _vat_rate_e = 0.23 if "23" in _vat_str_e else 0.0
                                    _freight_e  = float(deal.get("Frete (€)") or 0)

                                    eh = st.columns([0.6, 1.0, 1.3, 2.8, 1.2, 1.2, 1.2, 1.2])
                                    for col, lbl in zip(eh, ["Qty","SKU","EAN","Produto","FC Final","Margem %","Preço Cliente","Total"]):
                                        col.caption(lbl)

                                    new_skus = {}
                                    for sku, info in _skus_edit.items():
                                        d        = info.get("data") or {}
                                        fc_final = float(info.get("fc_final") or d.get("ufc_raw") or 0)
                                        old_pvp  = float(info.get("pvp") or fc_final)
                                        old_qty  = int(info.get("qty") or 1)
                                        ean      = d.get("ean") or "—"
                                        name     = f"{d.get('brand','')} · {d.get('name','')}"

                                        # Margem gross atual: (pvp - fc) / pvp * 100
                                        _cur_margin = round(((old_pvp - fc_final) / old_pvp * 100) if old_pvp > 0 else 0.0, 1)

                                        ec = st.columns([0.6, 1.0, 1.3, 2.8, 1.2, 1.2, 1.2, 1.2])
                                        if f"eq_{did}_{sku}" not in st.session_state:
                                            st.session_state[f"eq_{did}_{sku}"] = old_qty
                                        if f"em_{did}_{sku}" not in st.session_state:
                                            st.session_state[f"em_{did}_{sku}"] = _cur_margin

                                        new_qty = ec[0].number_input("", min_value=1, step=1,
                                                                      key=f"eq_{did}_{sku}",
                                                                      label_visibility="collapsed")
                                        ec[1].markdown(f"`{sku}`")
                                        ec[2].markdown(f"`{ean}`")
                                        ec[3].markdown(name)
                                        ec[4].markdown(f"{fc_final:.2f} €")

                                        new_margin_line = ec[5].number_input(
                                            "", min_value=0.0, max_value=99.9, step=0.5,
                                            format="%.1f", key=f"em_{did}_{sku}",
                                            label_visibility="collapsed",
                                            help="Margem bruta % — Preço Cliente é calculado automaticamente",
                                        )

                                        # pvp calculado da margem gross: pvp = fc / (1 - m/100)
                                        new_pvp = round(fc_final / (1 - new_margin_line / 100), 4) if new_margin_line < 100 else fc_final
                                        ec[6].markdown(f"**{new_pvp:.2f} €**")
                                        ec[7].markdown(f"**{new_pvp * new_qty:.2f} €**")

                                        new_info = dict(info)
                                        new_info["qty"]    = new_qty
                                        new_info["pvp"]    = new_pvp
                                        new_info["margin"] = round(new_margin_line, 2)
                                        new_skus[sku] = new_info

                                    # Totais
                                    _new_pvp_total  = sum(new_skus[s]["pvp"] * new_skus[s]["qty"] for s in new_skus)
                                    # Usar fc_final como base de custo (consistente com o cálculo do pvp por linha)
                                    _new_cost_total = sum(float(new_skus[s].get("fc_final") or (new_skus[s].get("data") or {}).get("ufc_raw") or 0) * new_skus[s]["qty"] for s in new_skus)
                                    _new_vat        = round(_new_pvp_total * _vat_rate_e, 2)
                                    _new_total      = round(_new_pvp_total + _freight_e + _new_vat, 2)
                                    _new_margin_pct = ((_new_pvp_total - _new_cost_total) / _new_pvp_total * 100) if _new_pvp_total else 0

                                    st.markdown(f"**Subtotal:** {_new_pvp_total:.2f} € &nbsp;|&nbsp; "
                                                f"**Frete:** {_freight_e:.2f} € &nbsp;|&nbsp; "
                                                f"**Total:** {_new_total:.2f} € &nbsp;|&nbsp; "
                                                f"**Margem:** {_new_margin_pct:.1f}%")

                                    if st.button("💾 Guardar Alterações de Preços", key=f"save_prices_{did}", type="primary"):
                                        ok = update_deal_prices(did, new_skus, _new_total, _new_margin_pct)
                                        if ok:
                                            st.success(f"✅ Preços do deal **{did}** atualizados!")
                                            st.session_state.pop(_edit_key, None)
                                            st.rerun()
                                        else:
                                            st.error("Erro ao guardar. Tenta novamente.")

                    # ── Atualizar status ────────────────────────────────────────
                    st.markdown("---")
                    u1, u2, u3 = st.columns([2,3,1])
                    new_st   = u1.selectbox("Status", STATUSES, key=f"sel_{did}",
                                            index=STATUSES.index(status) if status in STATUSES else 0)
                    new_note = u2.text_input("Nota", key=f"note_{did}")
                    u3.markdown("<br>", unsafe_allow_html=True)
                    if u3.button("💾 Guardar", key=f"upd_{did}"):
                        update_status(did, new_st, new_note)
                        st.success(f"✅ {did} → {new_st}")
                        st.rerun()

                    # ── Reenviar Proposta ──────────────────────────────────────
                    st.markdown("---")
                    st.markdown("**📧 Enviar Proposta**")
                    rp1, rp2 = st.columns([4, 1])
                    resend_to = rp1.text_input(
                        "Email(s) destinatário(s)",
                        value=str(deal.get("Email Cliente", "")),
                        key=f"rto_{did}",
                        help="Separa vários emails com ;",
                    )
                    rp2.markdown("<br>", unsafe_allow_html=True)
                    if rp2.button("🚀 Gerar & Enviar", key=f"rsend_{did}", type="primary",
                                   use_container_width=True):
                        _skus = deal.get("_skus_detail") or {}
                        if not _skus:
                            st.warning("Sem dados de produtos para regenerar a proposta.")
                        else:
                            _vat_str  = str(deal.get("IVA", ""))
                            _vat_rate = 0.23 if "23" in _vat_str else 0.0
                            _freight  = float(deal.get("Frete (€)") or 0)
                            with st.spinner("A gerar proposta com Claude AI..."):
                                try:
                                    # Filtrar notas internas (ex: "Duplicado de BM-...") — não expor ao cliente
                                    _raw_notes = str(deal.get("Notas", "") or "")
                                    _email_notes = "\n".join(
                                        l for l in _raw_notes.splitlines()
                                        if not l.strip().lower().startswith("duplicado de")
                                        and not l.strip().lower().startswith("[")
                                    ).strip()
                                    html_body, pvp_calc, margin_calc = generate_proposal(
                                        client_name=str(deal.get("Cliente", "")),
                                        client_email=resend_to,
                                        country=str(deal.get("País", "")),
                                        language=str(deal.get("Língua", "EN")),
                                        skus_data=_skus,
                                        deal_id=did,
                                        notes=_email_notes,
                                        incoterm=str(deal.get("Incoterm", "")),
                                        payment_conditions=str(deal.get("Pagamento", "")),
                                        freight_cost=_freight,
                                        vat_rate=_vat_rate,
                                        availability=str(deal.get("Availability / ETA", "Ex-stock")),
                                        company=str(deal.get("company", "") or ""),
                                    )
                                    st.session_state["pending_email"] = {
                                        "html_body":   html_body,
                                        "deal_id":     did,
                                        "pvp_total":   pvp_calc,
                                        "margin_calc": margin_calc,
                                        "client_email": resend_to,
                                        "client_name": str(deal.get("Cliente", "")),
                                        "company":     str(deal.get("company", "") or ""),
                                        "language":    str(deal.get("Língua", "EN")),
                                    }
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao gerar proposta: {e}")
                                    import traceback; st.code(traceback.format_exc())

                    # ── Follow-up (só se deal em status activo) ────────────────
                    if status in ("Lead", "Pedido de Cotação", "Rascunho", "Enviado", "Em Negociação", "Follow-up"):
                        st.markdown("**Follow-up**")
                        fu1, fu2 = st.columns(2)
                        days    = fu1.number_input("Dias desde o envio", min_value=1, value=7,
                                                   step=1, key=f"days_{did}")
                        fu_note = fu2.text_input("Notas follow-up", key=f"funote_{did}")
                        if st.button("✉️  Gerar Follow-up com Claude AI", key=f"fu_{did}"):
                            with st.spinner("A gerar follow-up..."):
                                try:
                                    html = generate_followup(deal, str(deal.get("Língua","EN")),
                                                             int(days), fu_note)
                                    html = html.strip()
                                    if html.startswith("```"): html = html.split("\n",1)[-1]
                                    if html.endswith("```"):   html = html.rsplit("```",1)[0]
                                    html = html.strip()
                                    save_email_html(did, html, "followup")
                                    update_status(did, "Follow-up", fu_note or f"Follow-up ({days}d)")
                                    st.success("✅ Follow-up gerado!")
                                    with st.expander("👁️ Pré-visualizar", expanded=True):
                                        st.components.v1.html(html, height=350, scrolling=True)
                                    fu_to  = str(deal.get("Email Cliente",""))
                                    fu_sub = build_subject(did, cl, str(deal.get("Língua","EN")),
                                                           company=str(deal.get("company","") or ""))
                                    fu_sub = fu_sub.replace("Commercial Proposal","Follow-up")
                                    if fu_to:
                                        if st.button("🚀 Enviar Follow-up", key=f"fu_send_{did}", type="primary"):
                                            ok, err = create_draft(fu_to, fu_sub, html, send=True)
                                            if ok:
                                                st.success("✅ Follow-up enviado!")
                                            else:
                                                st.error(f"Erro: {err}")
                                except Exception as e:
                                    st.error(f"Erro: {e}")
                                    import traceback; st.code(traceback.format_exc())

                    # ── Duplicar / Apagar Deal ─────────────────────────────────
                    if _role in CAN_EDIT_DEALS:
                        st.markdown("---")
                        da1, da2 = st.columns(2)

                        # Duplicar
                        with da1:
                            st.markdown("**📋 Duplicar Deal**")
                            dup_contact = st.text_input("Nome do contacto *", key=f"dup_cl_{did}",
                                                         placeholder="Ex: João Silva")
                            dup_company = st.text_input("Empresa", key=f"dup_co_{did}",
                                                         placeholder="Ex: Flying Shrimp Ltd")
                            dup_email   = st.text_input("Email *", key=f"dup_em_{did}",
                                                         placeholder="Ex: joao@empresa.com")
                            dup_country = st.text_input("País", key=f"dup_ct_{did}",
                                                         placeholder="Ex: Poland",
                                                         value=cntry)
                            if st.button("📋 Duplicar para este cliente", key=f"dup_btn_{did}"):
                                if dup_contact and dup_email:
                                    new_id = duplicate_deal(
                                        did, dup_contact, dup_email, dup_country,
                                        new_company=dup_company,
                                    )
                                    if new_id:
                                        st.success(f"✅ Deal duplicado → **{new_id}** criado como Rascunho.")
                                        st.rerun()
                                    else:
                                        st.error("Erro ao duplicar. Tenta novamente.")
                                else:
                                    st.warning("Preenche o nome do contacto e email.")

                        # Apagar
                        with da2:
                            st.markdown("**🗑️ Apagar Deal**")
                            st.caption("⚠️ Esta ação é irreversível — o deal será eliminado permanentemente.")
                            _confirm_key = f"confirm_del_{did}"
                            if not st.session_state.get(_confirm_key):
                                if st.button("🗑️ Apagar Deal", key=f"del_btn_{did}", type="secondary"):
                                    st.session_state[_confirm_key] = True
                                    st.rerun()
                            else:
                                st.warning(f"Tens a certeza que queres apagar **{did}**?")
                                c_yes, c_no = st.columns(2)
                                if c_yes.button("✅ Sim, apagar", key=f"del_yes_{did}", type="primary"):
                                    if delete_deal(did):
                                        st.session_state.pop(_confirm_key, None)
                                        st.success(f"✅ Deal **{did}** apagado.")
                                        st.rerun()
                                    else:
                                        st.error("Erro ao apagar.")
                                if c_no.button("❌ Cancelar", key=f"del_no_{did}"):
                                    st.session_state.pop(_confirm_key, None)
                                    st.rerun()

                        # ── Campos Operacionais ─────────────────────────────────────
                        st.markdown("---")
                        st.markdown("**📦 Dados Operacionais & Logísticos**")
                        _op_c1, _op_c2, _op_c3 = st.columns(3)
                        _op_order_date  = _op_c1.text_input("Data Encomenda",
                            value=str(deal.get("Data Encomenda","") or ""),
                            placeholder="YYYY-MM-DD", key=f"op_od_{did}")
                        _op_exp_del     = _op_c2.text_input("Entrega Prevista",
                            value=str(deal.get("Entrega Prevista","") or ""),
                            placeholder="YYYY-MM-DD", key=f"op_ed_{did}")
                        _op_act_del     = _op_c3.text_input("Entrega Real",
                            value=str(deal.get("Entrega Real","") or ""),
                            placeholder="YYYY-MM-DD", key=f"op_ad_{did}")

                        _op_c4, _op_c5, _op_c6 = st.columns(3)
                        _op_inv_num     = _op_c4.text_input("Nº Fatura",
                            value=str(deal.get("Nº Fatura","") or ""),
                            key=f"op_in_{did}")
                        _op_inv_date    = _op_c5.text_input("Data Fatura",
                            value=str(deal.get("Data Fatura","") or ""),
                            placeholder="YYYY-MM-DD", key=f"op_id_{did}")
                        _op_inv_val     = _op_c6.number_input("Valor Fatura (€)",
                            min_value=0.0, step=0.01, format="%.2f",
                            value=float(deal.get("Valor Fatura (€)") or 0),
                            key=f"op_iv_{did}")

                        _op_c7, _op_c8, _op_c9 = st.columns(3)
                        _op_cmr         = _op_c7.text_input("CMR Nº",
                            value=str(deal.get("CMR Nº","") or ""),
                            key=f"op_cmr_{did}")
                        _op_pl          = _op_c8.text_input("Packing List Nº",
                            value=str(deal.get("Packing List Nº","") or ""),
                            key=f"op_pl_{did}")
                        _op_sup         = _op_c9.text_input("Fornecedor(es)",
                            value=str(deal.get("Fornecedor(es)","") or ""),
                            placeholder="Ex: Philips, Braun",
                            key=f"op_sup_{did}")

                        if st.button("💾 Guardar Operacional", key=f"op_save_{did}", type="secondary"):
                            _op_ok = update_deal_operational(
                                did,
                                order_date        = _op_order_date or None,
                                expected_delivery = _op_exp_del   or None,
                                actual_delivery   = _op_act_del   or None,
                                invoice_number    = _op_inv_num   or None,
                                invoice_date      = _op_inv_date  or None,
                                invoice_value     = _op_inv_val   if _op_inv_val > 0 else None,
                                cmr_number        = _op_cmr       or None,
                                packing_list      = _op_pl        or None,
                                supplier_ids      = _op_sup       or None,
                            )
                            if _op_ok:
                                st.success("✅ Dados operacionais guardados!")
                                st.rerun()
                            else:
                                st.error("Erro ao guardar dados operacionais.")

                    # ── Confirmação de Expedição ────────────────────────────────
                    if status in ("Expedido", "Entregue"):
                        st.markdown("---")
                        st.markdown("**📬 Confirmação de Expedição**")
                        _exp_c1, _exp_c2 = st.columns(2)
                        _exp_carrier = _exp_c1.text_input(
                            "Transportadora",
                            value=str(deal.get("Fornecedor(es)","") or ""),
                            key=f"exp_carrier_{did}",
                        )
                        _exp_cmr = _exp_c2.text_input(
                            "CMR / Guia Nº",
                            value=str(deal.get("CMR Nº","") or ""),
                            key=f"exp_cmr_{did}",
                        )
                        _exp_c3, _exp_c4 = st.columns(2)
                        _exp_tracking = _exp_c3.text_input("Tracking / Referência", key=f"exp_track_{did}")
                        _exp_eta = _exp_c4.text_input(
                            "Entrega Prevista",
                            value=str(deal.get("Entrega Prevista","") or ""),
                            key=f"exp_eta_{did}",
                        )
                        _exp_lang = str(deal.get("Língua","EN") or "EN")
                        if st.button("📬 Gerar Email de Confirmação", key=f"exp_gen_{did}", type="secondary"):
                            with st.spinner("A gerar..."):
                                try:
                                    _exp_html = generate_expedition_confirmation(
                                        deal         = deal,
                                        carrier      = _exp_carrier,
                                        cmr_number   = _exp_cmr,
                                        tracking     = _exp_tracking,
                                        estimated_delivery = _exp_eta,
                                        language     = _exp_lang,
                                    )
                                    st.session_state[f"exp_html_{did}"] = _exp_html
                                except Exception as _e:
                                    st.error(f"Erro: {_e}")
                        if st.session_state.get(f"exp_html_{did}"):
                            _eh = st.session_state[f"exp_html_{did}"]
                            with st.expander("👁️ Pré-visualizar", expanded=True):
                                st.components.v1.html(_eh, height=400, scrolling=True)
                            _exp_to = st.text_input(
                                "Enviar para",
                                value=str(deal.get("Email Cliente","") or ""),
                                key=f"exp_to_{did}",
                            )
                            _exp_cc = st.text_input("CC", value="", key=f"exp_cc_{did}",
                                                     help="Separa múltiplos emails com ;")
                            if st.button("🚀 Enviar Confirmação", key=f"exp_send_{did}", type="primary"):
                                _exp_subj = f"Shipment Confirmation — {did}" if _exp_lang == "EN" else f"Confirmación de Envío — {did}" if _exp_lang == "ES" else f"Confirmation d'Expédition — {did}" if _exp_lang == "FR" else f"Confirmação de Expedição — {did}"
                                _exp_cc_list = [e.strip() for e in _exp_cc.split(";") if e.strip()] or None
                                _ok, _err = create_draft(_exp_to, _exp_subj, _eh, send=True, cc=_exp_cc_list)
                                if _ok:
                                    update_status(did, "Entregue", f"Confirmação de expedição enviada. CMR: {_exp_cmr}")
                                    st.success("✅ Email de confirmação enviado!")
                                    st.session_state.pop(f"exp_html_{did}", None)
                                    st.rerun()
                                else:
                                    st.error(f"Erro: {_err}")

                    # ── Fechar Deal ─────────────────────────────────────────────
                    st.markdown("---")
                    st.markdown("**🔒 Fechar Deal**")
                    fd1, fd2 = st.columns(2)
                    dep_date    = fd1.text_input("Data prevista de saída (cliente)",
                                                 placeholder="ex: 15/04/2026",
                                                 key=f"dep_{did}")
                    supplier_date = fd2.text_input("Data acordada c/ fornecedor (entrega Worten)",
                                                   placeholder="ex: 10/04/2026",
                                                   key=f"supdate_{did}")
                    fd3, fd4, fd5 = st.columns(3)
                    stocks_to = fd3.text_input("Email Stocks",
                                               value=STOCKS_EMAIL,
                                               key=f"sto_{did}",
                                               help="Separa vários emails com ;")
                    admin_to = fd4.text_input("Email Administrativo",
                                              value=ADMIN_EMAIL,
                                              key=f"adm_{did}",
                                              help="Separa vários emails com ;")
                    fd5.markdown("<br>", unsafe_allow_html=True)
                    if fd5.button("✅ Fechar & Enviar Alertas Internos",
                                  key=f"close_{did}", type="primary",
                                  use_container_width=True):
                        if not dep_date:
                            st.warning("Indica a data prevista de saída.")
                        elif not (stocks_to or admin_to):
                            st.warning("Indica pelo menos um email de destino.")
                        else:
                            with st.spinner("A gerar e enviar alertas internos..."):
                                try:
                                    stocks_html, admin_html = generate_closing_emails(
                                        deal, dep_date, supplier_date)
                                    errs = []
                                    subj = f"[DEAL FECHADO] {did} — {cl}"
                                    if stocks_to:
                                        ok, e = create_draft(stocks_to, f"{subj} | Stocks", stocks_html, send=True)
                                        if not ok: errs.append(f"Stocks: {e}")
                                    if admin_to:
                                        ok, e = create_draft(admin_to, f"{subj} | Administrativo", admin_html, send=True)
                                        if not ok: errs.append(f"Admin: {e}")
                                    update_status(did, "Fechado", f"Deal fechado. Saída: {dep_date}")
                                    if errs:
                                        st.error("Erros: " + " | ".join(errs))
                                    else:
                                        st.success(f"✅ Deal {did} fechado! Alertas enviados.")
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"Erro: {e}")
                                    import traceback; st.code(traceback.format_exc())

        st.caption("💾 Dados guardados em Supabase")


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 3 — PEDIDO FORNECEDOR
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏭  Pedido Fornecedor":
    st.title("🏭 Pedido de Cotação / Aprovação — Fornecedor")
    st.caption("Valida custos e negociação SO antes de emitir proposta ao cliente.")

    if "sup_basket" not in st.session_state:
        st.session_state["sup_basket"] = {}
    if "sup_so_manual" not in st.session_state:
        st.session_state["sup_so_manual"] = {}

    idx = load_index()

    # ── Pesquisa SKU ──────────────────────────────────────────────────────────
    st.subheader("Adicionar Produtos")
    s1, s2 = st.columns([2, 1])
    with s1:
        sup_search_mode = st.radio("Pesquisar por", ["SKU ID","EAN","Nome"], horizontal=True, key="sup_sm")
    sup_col_a, sup_col_b = st.columns([3, 1])
    with sup_col_a:
        if sup_search_mode == "SKU ID":
            sup_raw = st.text_input("SKU ID(s) — separa por vírgula ou espaço", key="sup_ids")
        elif sup_search_mode == "EAN":
            sup_raw = st.text_input("EAN(s) — separa por vírgula ou espaço", key="sup_ean")
        else:
            sup_raw = st.text_input("Nome do produto", key="sup_name")

    btn_sup_add, btn_sup_clear = st.columns([2, 6])
    if btn_sup_add.button("➕ Adicionar", key="sup_add"):
        if sup_raw.strip():
            if sup_search_mode == "Nome":
                found = search_by_name(sup_raw.strip(), idx)
            else:
                ids = [x.strip() for x in sup_raw.replace(",", " ").split() if x.strip()]
                found = lookup_skus(ids, idx)
            if not found:
                st.warning("Nenhum SKU encontrado.")
            else:
                for ref, d in found.items():
                    sku_id = d.get("sku_id", ref)
                    st.session_state["sup_basket"][sku_id] = d
                    if sku_id not in st.session_state["sup_so_manual"]:
                        st.session_state["sup_so_manual"][sku_id] = 0.0
                st.rerun()
    if btn_sup_clear.button("🗑️ Limpar", key="sup_clear"):
        st.session_state["sup_basket"] = {}
        st.session_state["sup_so_manual"] = {}
        st.rerun()

    # ── Margem Alvo + estado de PVP Alvo ─────────────────────────────────────
    if "sup_pvp_alvo" not in st.session_state:
        st.session_state["sup_pvp_alvo"] = {}

    _ta_col1, _ta_col2 = st.columns([2, 6])
    sup_target_margin = _ta_col1.number_input(
        "🎯 Margem Alvo (%)",
        min_value=0.0, max_value=60.0,
        value=st.session_state.get("sup_target_margin", TARGET_MARGIN_DEFAULT),
        step=0.5, format="%.1f",
        help="Margem pretendida para calcular o Apoio Adicional a solicitar ao fornecedor. "
             "Define o PVP Alvo por linha para activar o cálculo.",
        key="sup_target_margin_input",
    )
    st.session_state["sup_target_margin"] = sup_target_margin

    # ── Tabela de produtos ────────────────────────────────────────────────────
    sup_basket = st.session_state["sup_basket"]
    if sup_basket:
        st.markdown("---")
        # Cabeçalho — com colunas de apoio adicional
        sh = st.columns([0.7, 1.1, 1.4, 3.0, 1.5, 1.5, 1.5, 1.5, 1.5, 0.5])
        for col, lbl in zip(sh, ["Qty","SKU","EAN","Produto",
                                   "FC Simulador","SO Negoc. (€)","FC Final",
                                   "PVP Alvo (€)","Apoio Adic.","✕"]):
            col.caption(lbl)
        st.markdown("---")

        sup_qty_map = {}
        for sku, d in list(sup_basket.items()):
            ufc_raw   = d.get("ufc_raw")
            eis_total = d.get("eis_total") or 0.0
            sell_out  = d.get("sell_out") or 0.0
            ean       = d.get("ean") or "—"
            name      = f"{d.get('brand','')} · {d.get('name','')[:35]}"

            sc = st.columns([0.7, 1.1, 1.4, 3.0, 1.5, 1.5, 1.5, 1.5, 1.5, 0.5])
            if f"sqty_{sku}" not in st.session_state:
                st.session_state[f"sqty_{sku}"] = 1
            sup_qty_map[sku] = sc[0].number_input("", min_value=1, step=1,
                                                   key=f"sqty_{sku}", label_visibility="collapsed")
            sc[1].markdown(f"**`{sku}`**")
            sc[2].markdown(f"`{ean}`")
            sc[3].markdown(name)

            # FC Simulador (exportação por defeito)
            if ufc_raw is not None:
                fc_sim = round(ufc_raw - eis_total + sell_out, 4)
                sc[4].markdown(f"**{fmt4(fc_sim)}**")
            else:
                fc_sim = None
                sc[4].markdown("⚠️ N/D")

            # SO negociação manual
            so_neg = sc[5].number_input("", min_value=0.0,
                                         value=st.session_state["sup_so_manual"].get(sku, 0.0),
                                         step=0.5, format="%.2f", key=f"sso_{sku}",
                                         label_visibility="collapsed",
                                         help="Apoio Sell-Out já negociado (€/un.)")
            st.session_state["sup_so_manual"][sku] = so_neg

            fc_final = round(fc_sim - so_neg, 4) if fc_sim is not None else None
            sc[6].markdown(f"**{fmt4(fc_final)}**" if fc_final is not None else "—")

            # PVP Alvo — preço que queremos praticar com o cliente
            pvp_alvo = sc[7].number_input("", min_value=0.0,
                                           value=st.session_state["sup_pvp_alvo"].get(sku, 0.0),
                                           step=1.0, format="%.2f", key=f"spvp_{sku}",
                                           label_visibility="collapsed",
                                           help="PVP pretendido ao cliente — calcula o Apoio Adicional necessário")
            st.session_state["sup_pvp_alvo"][sku] = pvp_alvo

            # Apoio Adicional Solicitado
            if pvp_alvo > 0 and fc_final is not None and sup_target_margin > 0:
                fc_max     = round(pvp_alvo * (1 - sup_target_margin / 100), 4)
                apoio_adic = round(max(0.0, fc_final - fc_max), 4)
                _acolor    = "#007700" if apoio_adic > 0 else "#999"
                _albl      = f"+{apoio_adic:.4f}" if apoio_adic > 0 else "✅ 0"
                sc[8].markdown(
                    f'<span style="color:{_acolor};font-weight:700;">{_albl}</span>',
                    unsafe_allow_html=True
                )
            else:
                sc[8].markdown("—")

            if sc[9].button("✕", key=f"srm_{sku}"):
                del st.session_state["sup_basket"][sku]
                st.session_state["sup_so_manual"].pop(sku, None)
                st.session_state["sup_pvp_alvo"].pop(sku, None)
                st.rerun()

        # Actualizar qtds no basket
        for sku in sup_basket:
            if sku in sup_qty_map:
                st.session_state["sup_basket"][sku]["_qty_override"] = sup_qty_map[sku]

        st.markdown("---")
        # ── Acções ───────────────────────────────────────────────────────────
        act1, act2 = st.columns(2)

        if act1.button("📄 Gerar Pedido ao Fornecedor", type="primary", use_container_width=True):
            _sup_skus_with_qty = {}
            for sku, d in sup_basket.items():
                _sup_skus_with_qty[sku] = {
                    "qty": sup_qty_map.get(sku, 1),
                    "data": d,
                    "so_neg": st.session_state["sup_so_manual"].get(sku, 0.0),
                }
            _html = generate_supplier_request(
                skus_data=_sup_skus_with_qty,
                so_manual=st.session_state["sup_so_manual"],
                vat_rate=0.0,
                target_margin=st.session_state.get("sup_target_margin", TARGET_MARGIN_DEFAULT),
                pvp_alvo_map=st.session_state.get("sup_pvp_alvo", {}),
            )
            st.session_state["sup_request_html"] = _html
            st.rerun()

        if act2.button("➡️ Usar para Nova Cotação Cliente", use_container_width=True,
                       help="Copia estes produtos e SOs para a Nova Cotação"):
            # Copiar basket e SO para a Nova Cotação
            _new_basket = {}
            _new_so = {}
            for sku, d in sup_basket.items():
                _d = dict(d)
                _new_basket[sku] = _d
                _new_so[sku] = st.session_state["sup_so_manual"].get(sku, 0.0)
            st.session_state["product_basket"] = _new_basket
            st.session_state["so_manual"]       = _new_so
            st.session_state["nav"]             = "🆕  Nova Cotação"
            st.rerun()

        # Pré-visualização do pedido gerado
        if "sup_request_html" in st.session_state:
            st.subheader("📄 Pedido Gerado")
            st.components.v1.html(st.session_state["sup_request_html"], height=520, scrolling=True)
            st.download_button(
                "⬇️ Descarregar HTML",
                data=st.session_state["sup_request_html"],
                file_name="pedido_fornecedor.html",
                mime="text/html",
                use_container_width=True,
            )
    else:
        st.info("Adiciona produtos para criar o pedido ao fornecedor.")


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 3 — CRM — CLIENTES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "👥  CRM — Clientes":
    import pandas as pd

    st.title("👥 CRM — Clientes B2B")

    # ── Tabs principais ───────────────────────────────────────────────────────
    tab_list, tab_new, tab_seg, tab_import, tab_quality = st.tabs([
        "📋 Lista de Clientes", "➕ Novo Cliente", "🎯 Segmentação", "📥 Importar", "🔍 Qualidade de Dados"
    ])

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — LISTA
    # ════════════════════════════════════════════════════════════════════════
    with tab_list:
        # Filtros
        fc1, fc2, fc3, fc4, fc5 = st.columns([2, 1.5, 1.5, 1.5, 1.5])
        crm_search   = fc1.text_input("Pesquisar empresa", placeholder="Nome...", key="crm_search")
        crm_status   = fc2.selectbox("Status", ["Todos"] + CLIENT_STATUSES, key="crm_status")
        crm_market   = fc3.selectbox("Mercado", ["Todos"] + MARKETS, key="crm_market")
        crm_type     = fc4.selectbox("Tipo", ["Todos"] + CLIENT_TYPES, key="crm_type")
        crm_country  = fc5.text_input("País", placeholder="Ex: Poland", key="crm_country")

        clients = list_clients(
            status      = None if crm_status  == "Todos" else crm_status,
            market      = None if crm_market  == "Todos" else crm_market,
            client_type = None if crm_type    == "Todos" else crm_type,
            country     = crm_country or None,
            search      = crm_search or None,
        )

        st.caption(f"{len(clients)} cliente(s)")

        if not clients:
            st.info("Sem clientes para os filtros selecionados.")
        else:
            STATUS_ICON = {"Ativo":"🟢","Inativo":"⚫","Prospeto":"🔵","Bloqueado":"🔴"}
            for c in clients:
                cid       = str(c.get("id",""))
                cname     = c.get("company_name","—")
                cctry     = c.get("country","—")
                cstat     = c.get("status","—")
                cemail    = c.get("contact_email","")
                ccontact  = c.get("contact_name","")
                ctype     = c.get("client_type","—")
                cphone    = c.get("contact_phone","")
                brands    = c.get("brands") or []

                _exp_sub  = f" · 👤 {ccontact}" if ccontact else ""
                with st.expander(
                    f"{STATUS_ICON.get(cstat,'⚪')} **{cname}** — {cctry}  ·  {ctype}  ·  {cstat}{_exp_sub}"
                ):
                    # ── Cabeçalho info ─────────────────────────────────────
                    i1, i2, i3, i4 = st.columns(4)
                    i1.markdown(f"**Email**  \n{cemail or '—'}")
                    i2.markdown(f"**Telefone**  \n{cphone or '—'}")
                    i3.markdown(f"**Mercado**  \n{c.get('market','—')}")
                    i4.markdown(f"**Incoterm**  \n{c.get('incoterm','—')}")

                    if brands:
                        st.markdown(f"**Marcas:** {', '.join(brands)}")
                    if c.get("notes"):
                        st.caption(f"📝 {c['notes'][:120]}")

                    # ── KPIs de Performance ────────────────────────────────
                    if cemail:
                        _kpis = get_client_kpis(cemail)
                        _k1, _k2, _k3, _k4, _k5 = st.columns(5)
                        _k1.metric("Faturado (Fechado)", f"{_kpis['total_revenue']:,.0f} €")
                        _k2.metric("Margem Média", f"{_kpis['avg_margin']:.1f}%")
                        _k3.metric("Total Deals", _kpis['deal_count'])
                        _k4.metric("Pipeline Ativo", f"{_kpis['active_pipeline']:,.0f} €")
                        _k5.metric("Última Atividade", _kpis['last_deal_date'])

                    # ── Histórico de deals ─────────────────────────────────
                    if cemail:
                        client_deals = get_client_deals(cemail)
                        if client_deals:
                            st.markdown("**Histórico de Deals**")
                            df_d = pd.DataFrame(client_deals)
                            df_d = df_d.rename(columns={
                                "deal_id":"Deal ID","created_at":"Data",
                                "status":"Status","proposed_value":"Valor (€)",
                                "margin_pct":"Margem","products":"Produtos",
                            })
                            cols_show = [c for c in ["Deal ID","Data","Status","Valor (€)","Margem","Produtos"] if c in df_d.columns]
                            st.dataframe(df_d[cols_show], use_container_width=True, hide_index=True)
                        else:
                            st.caption("Sem deals registados para este cliente.")

                    st.markdown("---")

                    # ── Editar cliente ─────────────────────────────────────
                    with st.expander("✏️ Editar dados do cliente", expanded=False):
                        full = get_client(cid)
                        if full:
                            e1, e2, e3 = st.columns(3)
                            e_company  = e1.text_input("Nome Empresa *", value=full.get("company_name",""), key=f"ec_{cid}")
                            e_legal    = e2.text_input("Nome Legal", value=full.get("legal_name",""), key=f"el_{cid}")
                            e_vat      = e3.text_input("VAT / NIF", value=full.get("vat",""), key=f"ev_{cid}")

                            e4, e5, e6 = st.columns(3)
                            e_country  = e4.text_input("País", value=full.get("country",""), key=f"eco_{cid}")
                            e_market   = e5.selectbox("Mercado", MARKETS,
                                index=MARKETS.index(full.get("market","EU")) if full.get("market") in MARKETS else 0,
                                key=f"em_{cid}")
                            e_ctype    = e6.selectbox("Tipo Cliente", CLIENT_TYPES,
                                index=CLIENT_TYPES.index(full.get("client_type","Distribuidor")) if full.get("client_type") in CLIENT_TYPES else 0,
                                key=f"ect_{cid}")

                            e7, e8 = st.columns(2)
                            e_addr   = e7.text_input("Morada", value=full.get("address",""), key=f"ea_{cid}")
                            e_city   = e8.text_input("Cidade", value=full.get("city",""), key=f"ecity_{cid}")

                            e12, e13 = st.columns(2)
                            e_inc    = e12.text_input("Incoterm", value=full.get("incoterm",""), key=f"einc_{cid}")
                            e_pay    = e13.text_input("Condições Pagamento", value=full.get("payment_terms",""), key=f"epay_{cid}")

                            # Marcas + Enriquecimento
                            _eb_col, _eb_btn = st.columns([4, 1])
                            e_brands = _eb_col.multiselect("Marcas", BRANDS_LIST,
                                default=[b for b in (full.get("brands") or []) if b in BRANDS_LIST],
                                key=f"ebr_{cid}")
                            if _eb_btn.button("🔍 Auto", key=f"ebrand_enrich_{cid}",
                                              help="Enriquecer marcas e categorias a partir do histórico de deals"):
                                with st.spinner("A analisar histórico de deals..."):
                                    _enr = enrich_brands_from_deals(full.get("contact_email",""))
                                st.success(
                                    f"✅ Marcas: +{_enr['brands_added']}  ·  "
                                    f"Categorias: +{_enr['categories_added']}"
                                )
                                st.rerun()

                            e_cats   = st.multiselect("Categorias", CATEGORIES_LIST,
                                default=[c2 for c2 in (full.get("categories") or []) if c2 in CATEGORIES_LIST],
                                key=f"ecat_{cid}")

                            e_stat   = st.selectbox("Status", CLIENT_STATUSES,
                                index=CLIENT_STATUSES.index(full.get("status","Ativo")) if full.get("status") in CLIENT_STATUSES else 0,
                                key=f"est_{cid}")
                            e_notes  = st.text_area("Notas", value=full.get("notes",""), height=70, key=f"en_{cid}")

                            if st.button("💾 Guardar Alterações", key=f"esave_{cid}", type="primary"):
                                ok = update_client(cid, {
                                    "company_name":  e_company,
                                    "legal_name":    e_legal,
                                    "vat":           e_vat,
                                    "country":       e_country,
                                    "market":        e_market,
                                    "client_type":   e_ctype,
                                    "address":       e_addr,
                                    "city":          e_city,
                                    "incoterm":      e_inc,
                                    "payment_terms": e_pay,
                                    "brands":        e_brands,
                                    "categories":    e_cats,
                                    "status":        e_stat,
                                    "notes":         e_notes,
                                })
                                if ok:
                                    st.success("✅ Cliente actualizado.")
                                    st.rerun()
                                else:
                                    st.error("Erro ao guardar.")

                    # ── Gestão de Contactos ────────────────────────────────
                    with st.expander("👤 Contactos", expanded=False):
                        _contacts = get_contacts(cid)

                        # Lista de contactos existentes
                        if _contacts:
                            st.markdown("**Contactos registados**")
                            for _ci, _ct in enumerate(_contacts):
                                _is_primary = _ct.get("primary", False)
                                _badge = "🌟 **Principal**" if _is_primary else f"#{_ci + 1}"
                                with st.container():
                                    _cc1, _cc2 = st.columns([5, 1])
                                    with _cc1:
                                        st.markdown(
                                            f"{_badge} — **{_ct.get('name','—')}**  ·  "
                                            f"_{_ct.get('role','') or 'Sem cargo'}_  \n"
                                            f"📧 {_ct.get('email','—')}  ·  📱 {_ct.get('phone','—')}"
                                            + (f"  \n🔗 {_ct.get('linkedin','')}" if _ct.get('linkedin') else "")
                                        )

                                    with _cc2:
                                        _btn_cols = st.columns(2)
                                        # Botão Apagar
                                        if _btn_cols[1].button("🗑️", key=f"del_ct_{cid}_{_ci}",
                                                               help="Remover contacto"):
                                            _new_cts = [c for i, c in enumerate(_contacts) if i != _ci]
                                            if save_contacts(cid, _new_cts):
                                                st.success("Contacto removido.")
                                                st.rerun()
                                        # Botão Definir como principal
                                        if not _is_primary:
                                            if _btn_cols[0].button("⭐", key=f"prim_ct_{cid}_{_ci}",
                                                                   help="Definir como contacto principal"):
                                                for _cx in _contacts:
                                                    _cx["primary"] = False
                                                _contacts[_ci]["primary"] = True
                                                if save_contacts(cid, _contacts):
                                                    st.success("Contacto principal actualizado.")
                                                    st.rerun()

                                    # Edição inline do contacto
                                    with st.expander(f"✏️ Editar contacto #{_ci + 1}", expanded=False):
                                        _ec1, _ec2 = st.columns(2)
                                        _ct_name   = _ec1.text_input("Nome", value=_ct.get("name",""), key=f"ctn_{cid}_{_ci}")
                                        _ct_role   = _ec2.selectbox("Cargo / Função", [""] + CONTACT_ROLES,
                                            index=([""] + CONTACT_ROLES).index(_ct.get("role","")) if _ct.get("role") in CONTACT_ROLES else 0,
                                            key=f"ctr_{cid}_{_ci}")
                                        _ec3, _ec4 = st.columns(2)
                                        _ct_email  = _ec3.text_input("Email", value=_ct.get("email",""), key=f"cte_{cid}_{_ci}")
                                        _ct_phone  = _ec4.text_input("Telefone", value=_ct.get("phone",""), key=f"ctp_{cid}_{_ci}")
                                        _ct_link   = st.text_input("LinkedIn", value=_ct.get("linkedin",""), key=f"ctl_{cid}_{_ci}")
                                        _ct_notes  = st.text_input("Notas", value=_ct.get("notes",""), key=f"ctno_{cid}_{_ci}")
                                        if st.button("💾 Guardar contacto", key=f"ctsave_{cid}_{_ci}"):
                                            _contacts[_ci].update({
                                                "name":     _ct_name,
                                                "role":     _ct_role,
                                                "email":    _ct_email,
                                                "phone":    _ct_phone,
                                                "linkedin": _ct_link,
                                                "notes":    _ct_notes,
                                            })
                                            if save_contacts(cid, _contacts):
                                                st.success("✅ Contacto guardado.")
                                                st.rerun()
                                            else:
                                                st.error("Erro ao guardar.")

                                st.divider()
                        else:
                            st.info("Ainda não há contactos registados.")

                        # Formulário para adicionar novo contacto
                        st.markdown("**➕ Adicionar contacto**")
                        _na1, _na2 = st.columns(2)
                        _new_ct_name  = _na1.text_input("Nome *", key=f"nct_name_{cid}")
                        _new_ct_role  = _na2.selectbox("Cargo / Função", [""] + CONTACT_ROLES, key=f"nct_role_{cid}")
                        _na3, _na4    = st.columns(2)
                        _new_ct_email = _na3.text_input("Email", key=f"nct_email_{cid}")
                        _new_ct_phone = _na4.text_input("Telefone", key=f"nct_phone_{cid}")
                        _new_ct_link  = st.text_input("LinkedIn", key=f"nct_link_{cid}")
                        _new_ct_notes = st.text_input("Notas", key=f"nct_notes_{cid}")
                        _set_primary  = st.checkbox("Definir como contacto principal", key=f"nct_prim_{cid}",
                                                    value=(len(_contacts) == 0))

                        if st.button("➕ Adicionar Contacto", key=f"nct_add_{cid}"):
                            if not _new_ct_name.strip():
                                st.warning("O nome do contacto é obrigatório.")
                            else:
                                _new_ct = {
                                    "name":     _new_ct_name.strip(),
                                    "role":     _new_ct_role,
                                    "email":    _new_ct_email.strip(),
                                    "phone":    _new_ct_phone.strip(),
                                    "linkedin": _new_ct_link.strip(),
                                    "notes":    _new_ct_notes.strip(),
                                    "primary":  _set_primary,
                                }
                                if _set_primary:
                                    for _xc in _contacts:
                                        _xc["primary"] = False
                                _contacts.append(_new_ct)
                                if save_contacts(cid, _contacts):
                                    st.success("✅ Contacto adicionado.")
                                    st.rerun()
                                else:
                                    st.error("Erro ao guardar.")

                    # ── Documentos KYC ─────────────────────────────────────
                    with st.expander("📎 Documentos KYC / Contrato", expanded=False):
                        _docs = get_client_documents(cid)
                        if _docs:
                            for _di, _doc in enumerate(_docs):
                                _d1, _d2 = st.columns([5, 1])
                                _d_url   = _doc.get("url","")
                                _d_link  = f"[🔗 Abrir]({_d_url})" if _d_url else "Sem link"
                                _d1.markdown(
                                    f"**{_doc.get('name','—')}** · `{_doc.get('type','—')}`  \n"
                                    f"{_d_link}  ·  {_doc.get('uploaded_at','')[:10]}  \n"
                                    + (f"_{_doc.get('notes','')}_" if _doc.get('notes') else "")
                                )
                                if _d2.button("🗑️", key=f"ddel_{cid}_{_di}", help="Remover documento"):
                                    if delete_client_document(cid, _di):
                                        st.success("Documento removido.")
                                        st.rerun()
                        else:
                            st.caption("Sem documentos registados.")

                        st.markdown("**➕ Adicionar documento**")
                        _da1, _da2 = st.columns(2)
                        _doc_name   = _da1.text_input("Nome do documento *", key=f"dname_{cid}")
                        _doc_type   = _da2.selectbox("Tipo", ["KYC","Contrato","Proposta","Declaração","Certificado","Outro"], key=f"dtype_{cid}")
                        _doc_url    = st.text_input("URL (SharePoint / Drive / link externo)", key=f"durl_{cid}")
                        _doc_file   = st.file_uploader("Ou carrega ficheiro", key=f"dfile_{cid}",
                                                        type=["pdf","xlsx","docx","png","jpg","csv"])
                        _doc_notes  = st.text_input("Notas", key=f"dnotes_{cid}")
                        if st.button("💾 Guardar Documento", key=f"dsave_{cid}"):
                            if not _doc_name.strip():
                                st.warning("O nome do documento é obrigatório.")
                            else:
                                _fb = _doc_file.read() if _doc_file else None
                                _fn = _doc_file.name if _doc_file else ""
                                ok = add_client_document(
                                    cid,
                                    name=_doc_name.strip(),
                                    doc_type=_doc_type,
                                    url=_doc_url.strip(),
                                    notes=_doc_notes.strip(),
                                    file_bytes=_fb,
                                    filename_storage=_fn,
                                )
                                if ok:
                                    st.success("✅ Documento guardado.")
                                    st.rerun()
                                else:
                                    st.error("Erro ao guardar documento.")

                    # ── Botão Nova Cotação para este cliente ───────────────
                    if st.button("✉️ Nova Cotação para este Cliente", key=f"nc_{cid}"):
                        full2 = get_client(cid) or c
                        st.session_state["crm_prefill"] = {
                            "client":   full2.get("company_name",""),
                            "email":    full2.get("contact_email",""),
                            "country":  full2.get("country",""),
                        }
                        st.session_state["nav"] = "🆕  Nova Cotação"
                        st.rerun()

    # ════════════════════════════════════════════════════════════════════════
    # ════════════════════════════════════════════════════════════════════════
    # TAB 3 — SEGMENTAÇÃO INTELIGENTE
    # ════════════════════════════════════════════════════════════════════════
    with tab_seg:
        st.subheader("🎯 Segmentação Inteligente de Clientes")
        st.markdown(
            "Identifica os clientes com maior **fit comercial** para uma proposta "
            "com base em marcas, categorias e histórico."
        )

        sg1, sg2, sg3 = st.columns(3)
        seg_brands   = sg1.multiselect("Marcas do produto", BRANDS_LIST, key="seg_brands")
        seg_cats     = sg2.multiselect("Categorias", CATEGORIES_LIST, key="seg_cats")
        seg_market   = sg3.selectbox("Mercado", ["Todos"] + MARKETS, key="seg_market")

        sg4, sg5, sg6 = st.columns(3)
        seg_ctype    = sg4.selectbox("Tipo de Cliente", ["Todos"] + CLIENT_TYPES, key="seg_ctype")
        seg_status   = sg5.selectbox("Status", ["Ativo","Todos"] + CLIENT_STATUSES, key="seg_status")
        seg_min_deals= sg6.number_input("Mínimo de deals históricos", min_value=0, value=0, step=1, key="seg_min_deals")

        if st.button("🔍 Segmentar Clientes", type="primary", key="btn_segment"):
            with st.spinner("A calcular fit scores..."):
                _seg_results = smart_segment(
                    brands      = seg_brands or [],
                    categories  = seg_cats or [],
                    market      = None if seg_market == "Todos" else seg_market,
                    client_type = None if seg_ctype == "Todos" else seg_ctype,
                    status_filter = None if seg_status == "Todos" else seg_status,
                    min_deals   = int(seg_min_deals),
                )
            st.session_state["seg_results"] = _seg_results

        if "seg_results" in st.session_state:
            _sr = st.session_state["seg_results"]
            st.caption(f"**{len(_sr)} clientes** encontrados — ordenados por fit comercial")

            if not _sr:
                st.info("Nenhum cliente corresponde aos critérios.")
            else:
                # Barra de progresso visual do fit score
                for _sr_c in _sr[:30]:  # máximo 30 resultados
                    _fs      = _sr_c.get("fit_score", 0)
                    _fs_color= "#007700" if _fs >= 60 else ("#CC7700" if _fs >= 35 else "#CC0000")
                    _sr_cid  = str(_sr_c.get("id",""))
                    _sr_em   = _sr_c.get("contact_email","")
                    _sr_name = _sr_c.get("company_name","—")
                    _sr_ct   = _sr_c.get("contact_name","")
                    _sr_ctry = _sr_c.get("country","—")
                    _sr_mrkt = _sr_c.get("market","—")
                    _sr_nd   = _sr_c.get("n_deals", 0)

                    _sc1, _sc2, _sc3 = st.columns([4, 2, 1])
                    with _sc1:
                        st.markdown(
                            f'<b>{_sr_name}</b> — {_sr_ctry} · {_sr_mrkt}'
                            f'{"  ·  👤 " + _sr_ct if _sr_ct else ""}  \n'
                            f'`{_sr_em}`  ·  {_sr_nd} deal(s) histórico',
                            unsafe_allow_html=True
                        )
                    with _sc2:
                        st.markdown(
                            f'<div style="background:#f0f0f0;border-radius:4px;padding:4px 8px;">'
                            f'<b style="color:{_fs_color};">Fit: {_fs}/100</b>  '
                            f'🏷️ {_sr_c.get("brand_score",0)} '
                            f'📦 {_sr_c.get("cat_score",0)} '
                            f'📈 {_sr_c.get("activity_score",0)}'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                    with _sc3:
                        if st.button("✉️", key=f"seg_nc_{_sr_cid}",
                                     help=f"Nova cotação para {_sr_name}"):
                            st.session_state["crm_prefill"] = {
                                "client":  _sr_c.get("contact_name",""),
                                "company": _sr_name,
                                "email":   _sr_em,
                                "country": _sr_ctry,
                            }
                            st.session_state["nav"] = "🆕  Nova Cotação"
                            st.rerun()
                    st.divider()

                # Exportar como CSV
                import pandas as _pd_seg
                _seg_export = _pd_seg.DataFrame([{
                    "Empresa":    r.get("company_name",""),
                    "País":       r.get("country",""),
                    "Mercado":    r.get("market",""),
                    "Contacto":   r.get("contact_name",""),
                    "Email":      r.get("contact_email",""),
                    "Fit Score":  r.get("fit_score",0),
                    "Deals":      r.get("n_deals",0),
                    "Tipo":       r.get("client_type",""),
                } for r in _sr])
                st.download_button(
                    "⬇️ Exportar lista (CSV)",
                    data=_seg_export.to_csv(index=False).encode("utf-8"),
                    file_name="segmentacao_clientes.csv",
                    mime="text/csv",
                )

    # TAB 2 — NOVO CLIENTE
    # ════════════════════════════════════════════════════════════════════════
    with tab_new:
        st.subheader("Novo Cliente")
        n1, n2, n3 = st.columns(3)
        new_company  = n1.text_input("Nome Empresa *", key="new_company")
        new_legal    = n2.text_input("Nome Legal / Faturação", key="new_legal")
        new_vat      = n3.text_input("VAT / NIF", key="new_vat")

        n4, n5, n6 = st.columns(3)
        new_country  = n4.text_input("País *", key="new_country")
        new_market   = n5.selectbox("Mercado", MARKETS, key="new_market")
        new_ctype    = n6.selectbox("Tipo de Cliente", CLIENT_TYPES, key="new_ctype")

        n7, n8, n9 = st.columns(3)
        new_addr     = n7.text_input("Morada", key="new_addr")
        new_zip      = n8.text_input("ZIP / Código Postal", key="new_zip")
        new_city     = n9.text_input("Cidade", key="new_city")

        st.markdown("**Contacto Principal**")
        c1, c2, c3, c4 = st.columns(4)
        new_cname    = c1.text_input("Nome", key="new_cname")
        new_crole    = c2.text_input("Cargo", key="new_crole")
        new_cemail   = c3.text_input("Email *", key="new_cemail")
        new_cphone   = c4.text_input("Telefone", key="new_cphone")
        new_linkedin = st.text_input("LinkedIn", key="new_linkedin")

        st.markdown("**Condições Comerciais**")
        p1, p2, p3 = st.columns(3)
        new_inc      = p1.text_input("Incoterm", placeholder="Ex: EXW — Ex Works", key="new_inc")
        new_pay      = p2.text_input("Condições Pagamento", placeholder="Ex: 100% T/T", key="new_pay")
        new_curr     = p3.selectbox("Moeda", ["EUR","USD","GBP","CHF"], key="new_curr")

        st.markdown("**Especialização**")
        new_brands   = st.multiselect("Marcas de Interesse", BRANDS_LIST, key="new_brands")
        new_cats     = st.multiselect("Categorias", CATEGORIES_LIST, key="new_cats")

        p4, p5 = st.columns(2)
        new_stat     = p4.selectbox("Status", CLIENT_STATUSES, key="new_stat")
        new_notes    = p5.text_area("Notas", height=80, key="new_notes")

        # Verificação de duplicados em tempo real
        if new_cemail or new_company or new_vat:
            _pre_dups = find_duplicates(email=new_cemail, company_name=new_company, vat=new_vat)
            if _pre_dups:
                st.warning(
                    "⚠️ **Possíveis duplicados encontrados:**  \n"
                    + "\n".join(
                        f"- **{d.get('company_name','—')}** · {d.get('contact_email','—')} "
                        f"· {d.get('country','—')} · {d.get('status','—')}"
                        for d in _pre_dups[:5]
                    )
                )

        if st.button("💾 Criar Cliente", type="primary", use_container_width=True, key="btn_new_client"):
            if not new_company or not new_country:
                st.error("⚠️ Preenche pelo menos o **Nome da Empresa** e o **País**.")
            else:
                cid_new = add_client({
                    "company_name":   new_company,
                    "legal_name":     new_legal,
                    "vat":            new_vat,
                    "country":        new_country,
                    "market":         new_market,
                    "client_type":    new_ctype,
                    "address":        new_addr,
                    "zip_code":       new_zip,
                    "city":           new_city,
                    "contact_name":   new_cname,
                    "contact_role":   new_crole,
                    "contact_email":  new_cemail,
                    "contact_phone":  new_cphone,
                    "contact_linkedin": new_linkedin,
                    "incoterm":       new_inc,
                    "payment_terms":  new_pay,
                    "currency":       new_curr,
                    "brands":         new_brands,
                    "categories":     new_cats,
                    "status":         new_stat,
                    "notes":          new_notes,
                })
                if cid_new:
                    st.success(f"✅ Cliente **{new_company}** criado (ID: {cid_new}).")
                    st.rerun()
                else:
                    st.error("Erro ao criar cliente.")

    # ════════════════════════════════════════════════════════════════════════
    # TAB 3 — IMPORTAR
    # ════════════════════════════════════════════════════════════════════════
    with tab_import:
        st.subheader("Importar Clientes via Excel")
        st.markdown("""
        Faz upload de um ficheiro Excel com os clientes. As colunas devem incluir:
        `company_name`, `country`, `contact_email` (obrigatórias) e opcionalmente:
        `legal_name`, `vat`, `market`, `city`, `address`, `zip_code`,
        `contact_name`, `contact_phone`, `client_type`, `incoterm`, `payment_terms`, `notes`
        """)

        uploaded = st.file_uploader("Ficheiro Excel (.xlsx)", type=["xlsx"], key="crm_upload")
        if uploaded:
            try:
                df_imp = pd.read_excel(uploaded)
                st.success(f"✅ {len(df_imp)} linhas detectadas")
                st.dataframe(df_imp.head(5), use_container_width=True, hide_index=True)

                if st.button("📥 Importar para CRM", type="primary", key="btn_import"):
                    rows = df_imp.where(pd.notnull(df_imp), None).to_dict("records")
                    for r in rows:
                        for arr_col in ("brands", "categories"):
                            if arr_col in r and isinstance(r[arr_col], str):
                                r[arr_col] = [x.strip() for x in r[arr_col].split(",") if x.strip()]
                            elif arr_col not in r:
                                r[arr_col] = []
                    with st.spinner(f"A importar {len(rows)} clientes..."):
                        ok_n, upd_n, err_n = bulk_import_clients(rows)
                    st.success(f"✅ {ok_n} novos clientes criados · {upd_n} actualizados.")
                    if err_n:
                        st.warning(f"⚠️ {err_n} erros.")
                    st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler ficheiro: {e}")

        st.markdown("---")
        st.subheader("🔄 Sincronizar Deals → CRM")
        st.markdown(
            "Cria ou enriquece automaticamente as entradas de clientes com base em todos os deals "
            "existentes. Para emails já na BD, apenas preenche campos em falta — **nunca sobrescreve**."
        )
        if st.button("🔄 Sincronizar agora", key="btn_sync_deals", type="secondary"):
            with st.spinner("A sincronizar deals com o CRM..."):
                _s_created, _s_existing = sync_clients_from_deals()
            st.success(
                f"✅ Sincronização concluída — "
                f"**{_s_created}** novos clientes criados · "
                f"**{_s_existing}** já existiam (enriquecidos se necessário)."
            )
            st.rerun()

        st.markdown("---")
        st.caption(f"Total de clientes na base de dados: **{count_clients()}**")

    # ════════════════════════════════════════════════════════════════════════
    # TAB 4 — QUALIDADE DE DADOS
    # ════════════════════════════════════════════════════════════════════════
    with tab_quality:
        st.subheader("🔍 Qualidade de Dados — CRM")
        st.markdown("Análise e correcção automática da BD de clientes.")

        qa1, qa2 = st.columns(2)
        if qa1.button("🔎 Analisar BD", type="primary", key="btn_qa_scan"):
            st.session_state["qa_report"] = data_quality_report()
        if qa2.button("✨ Auto-Enriquecer (market / currency / tipo)", key="btn_qa_enrich"):
            with st.spinner("A enriquecer..."):
                _res = auto_enrich_clients()
            st.success(f"✅ {_res['updated']} registos actualizados · {_res['unchanged']} sem alterações.")
            st.rerun()

        _qa = st.session_state.get("qa_report")
        if not _qa:
            st.info("Clica em **Analisar BD** para gerar o relatório.")
        else:
            _tot = _qa["total_clients"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Clientes", _tot)
            m2.metric("⚠️ Email/Domínio", len(_qa["email_domain_issues"]))
            m3.metric("📞 Telefone s/ indicativo", len(_qa["phone_issues"]))
            m4.metric("🔁 Possíveis duplicados", len(_qa["duplicates"]))
            st.divider()

            # ── 1. Problemas de domínio de email ─────────────────────────
            with st.expander(f"📧 Domínios de email inconsistentes ({len(_qa['email_domain_issues'])} empresa(s))",
                             expanded=len(_qa["email_domain_issues"]) > 0):
                if not _qa["email_domain_issues"]:
                    st.success("✅ Todos os emails por empresa têm domínio consistente.")
                else:
                    for issue in _qa["email_domain_issues"]:
                        st.warning(f"**{issue['company']}** — domínios: {', '.join(issue['domains'])}")
                        for e in issue["entries"]:
                            st.caption(f"  → `{e['email']}` (ID {e['id']})")

            # ── 2. Telefones sem indicativo ───────────────────────────────
            with st.expander(f"📞 Telefones sem indicativo de país ({len(_qa['phone_issues'])})",
                             expanded=len(_qa["phone_issues"]) > 0):
                if not _qa["phone_issues"]:
                    st.success("✅ Todos os telefones têm indicativo de país.")
                else:
                    if st.button("⚡ Corrigir todos automaticamente", key="btn_fix_all_phones"):
                        with st.spinner("A corrigir telefones..."):
                            _fixed, _skip = fix_all_phones()
                        st.success(f"✅ {_fixed} telefones corrigidos · {_skip} sem código de país disponível.")
                        st.session_state.pop("qa_report", None)
                        st.rerun()

                    for p in _qa["phone_issues"]:
                        _code_sug = p.get("suggested", "")
                        _label = (f"**{p['company']}** · {p['contact']} · `{p['phone']}` "
                                  f"· {p['country']}"
                                  + (f" → sugerido: **{_code_sug}**" if _code_sug else " (país sem código mapeado)"))
                        pc1, pc2 = st.columns([5, 1])
                        pc1.markdown(_label)
                        if _code_sug and pc2.button("✔️ Corrigir", key=f"fixph_{p['id']}"):
                            fix_phone_add_code(str(p["id"]), p["phone"], p["country"])
                            st.session_state.pop("qa_report", None)
                            st.rerun()

            # ── 3. Empresas duplicadas ────────────────────────────────────
            with st.expander(f"🔁 Possíveis empresas duplicadas ({len(_qa['duplicates'])} grupo(s))",
                             expanded=len(_qa["duplicates"]) > 0):
                if not _qa["duplicates"]:
                    st.success("✅ Sem duplicados detectados.")
                else:
                    for grp in _qa["duplicates"]:
                        names = " / ".join(c.get("company_name","—") for c in grp)
                        st.warning(f"Grupo similar: **{names}**")
                        _g_cols = st.columns(len(grp))
                        for gi, (gc, gcol) in enumerate(zip(grp, _g_cols)):
                            gcol.markdown(
                                f"**{gc.get('company_name','—')}**  \n"
                                f"{gc.get('contact_name','—')}  \n"
                                f"`{gc.get('contact_email','—')}`  \n"
                                f"{gc.get('country','—')} · {gc.get('status','—')}"
                            )
                        # Merge: escolher primary/secondary
                        ids    = [str(c["id"]) for c in grp]
                        labels = [c.get("company_name","—") for c in grp]
                        mg1, mg2, mg3 = st.columns([2, 2, 1])
                        _prim = mg1.selectbox("Manter (primary)", options=ids,
                                              format_func=lambda x: labels[ids.index(x)],
                                              key=f"mg_prim_{ids[0]}")
                        _sec  = mg2.selectbox("Apagar (secondary)", options=ids,
                                              format_func=lambda x: labels[ids.index(x)],
                                              key=f"mg_sec_{ids[0]}",
                                              index=1 if len(ids) > 1 else 0)
                        if mg3.button("🔀 Fazer Merge", key=f"mg_btn_{ids[0]}"):
                            if _prim == _sec:
                                st.error("Primary e secondary têm de ser diferentes.")
                            else:
                                ok = merge_clients(_prim, _sec)
                                if ok:
                                    st.success("✅ Merge concluído.")
                                    st.session_state.pop("qa_report", None)
                                    st.rerun()
                                else:
                                    st.error("Erro no merge.")
                        st.divider()

            # ── 4. Campos em falta ────────────────────────────────────────
            with st.expander(f"📋 Registos com campos importantes em falta ({len(_qa['missing_fields'])})",
                             expanded=False):
                if not _qa["missing_fields"]:
                    st.success("✅ Sem campos obrigatórios em falta.")
                else:
                    import pandas as _pd_qa
                    _mf_df = _pd_qa.DataFrame([
                        {"Empresa": r["company"], "Campos em Falta": ", ".join(r["missing"])}
                        for r in _qa["missing_fields"]
                    ])
                    st.dataframe(_mf_df, use_container_width=True, hide_index=True)
                    st.caption("Edita cada cliente na tab **Lista de Clientes** para completar os campos.")


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 3B — FORNECEDORES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🤝  Fornecedores":
    from supplier_tracker import (
        add_supplier, update_supplier, get_supplier, get_supplier_by_email,
        list_suppliers, count_suppliers, delete_supplier,
        find_duplicate_suppliers, get_supplier_contacts, save_supplier_contacts,
        supplier_quality_report, auto_fill_cgf_from_reference, merge_suppliers,
        get_supplier_deals, get_cgf_dashboard_data,
        SUPPLIER_STATUSES, SUPPLIER_TYPES, SUPPLIER_MARKETS,
        BRANDS_LIST as SUP_BRANDS, CATEGORIES_LIST as SUP_CATS,
        CONTACT_ROLES as SUP_ROLES, CGF_REFERENCE,
    )
    import pandas as pd

    st.title("🤝 Fornecedores — CRM")

    _sup_total = count_suppliers()
    st.caption(f"Base de dados: **{_sup_total}** fornecedor(es) registado(s)")

    tab_list, tab_new, tab_cgf, tab_quality = st.tabs([
        "📋 Lista de Fornecedores", "➕ Novo Fornecedor",
        "📊 Performance & CGF", "🔍 Qualidade de Dados",
    ])

    STATUS_ICON_SUP = {
        "Ativo": "🟢", "Em Negociação": "🔵",
        "Inativo": "⚫", "Bloqueado": "🔴"
    }

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — LISTA
    # ══════════════════════════════════════════════════════════════════════════
    with tab_list:
        sf1, sf2, sf3, sf4 = st.columns([2.5, 1.5, 1.5, 1.5])
        sup_search = sf1.text_input("Pesquisar fornecedor", placeholder="Nome ou marca...", key="sup_search")
        sup_status = sf2.selectbox("Status", ["Todos"] + SUPPLIER_STATUSES, key="sup_status")
        sup_type   = sf3.selectbox("Tipo", ["Todos"] + SUPPLIER_TYPES, key="sup_type")
        sup_ctry   = sf4.text_input("País", placeholder="Ex: Germany", key="sup_country")

        suppliers = list_suppliers(
            status        = None if sup_status == "Todos" else sup_status,
            supplier_type = None if sup_type   == "Todos" else sup_type,
            country       = sup_ctry or None,
            search        = sup_search or None,
        )

        st.caption(f"{len(suppliers)} resultado(s)")

        if not suppliers:
            st.info("Sem fornecedores para os filtros selecionados.")
        else:
            for s in suppliers:
                sid     = str(s.get("id", ""))
                sname   = s.get("supplier_name", "—")
                sbrand  = s.get("brand", "—")
                sctry   = s.get("country", "—")
                sstat   = s.get("status", "—")
                semail  = s.get("contact_email", "")
                scont   = s.get("contact_name", "")
                stype   = s.get("supplier_type", "—")
                scgf    = s.get("cgf") or 0
                sbrands = s.get("brands") or []

                _cgf_badge = f"  ·  CGF **{scgf:.1f}%**" if scgf else ""
                _cont_badge = f"  ·  👤 {scont}" if scont else ""

                with st.expander(
                    f"{STATUS_ICON_SUP.get(sstat,'⚪')} **{sname}**"
                    f"{' — ' + sbrand if sbrand and sbrand != sname else ''}"
                    f" — {sctry}  ·  {stype}{_cgf_badge}{_cont_badge}"
                ):
                    # ── Info rápida ─────────────────────────────────────────
                    si1, si2, si3, si4 = st.columns(4)
                    si1.markdown(f"**Email**  \n{semail or '—'}")
                    si2.markdown(f"**Telefone**  \n{s.get('contact_phone','') or '—'}")
                    si3.markdown(f"**Incoterm**  \n{s.get('incoterm','') or '—'}")
                    si4.markdown(f"**Pagamento**  \n{s.get('payment_terms','') or '—'}")

                    _si5, _si6, _si7 = st.columns(3)
                    _si5.metric("CGF / Rebate", f"{scgf:.1f}%" if scgf else "N/D")
                    _si6.metric("Pedido Mínimo", f"{s.get('min_order',0):,.0f} {s.get('currency','EUR')}" if s.get("min_order") else "—")
                    _si7.metric("Lead Time", s.get("lead_time","") or "—")

                    if sbrands:
                        st.markdown(f"**Marcas:** {', '.join(sbrands)}")
                    if s.get("categories"):
                        st.markdown(f"**Categorias:** {', '.join(s['categories'])}")
                    if s.get("notes"):
                        st.caption(f"📝 {s['notes'][:150]}")

                    st.markdown("---")

                    # ── Editar fornecedor ───────────────────────────────────
                    with st.expander("✏️ Editar dados do fornecedor", expanded=False):
                        full_s = get_supplier(sid)
                        if full_s:
                            se1, se2, se3 = st.columns(3)
                            s_name    = se1.text_input("Nome Fornecedor *", value=full_s.get("supplier_name",""), key=f"sn_{sid}")
                            s_legal   = se2.text_input("Nome Legal", value=full_s.get("legal_name",""), key=f"sleg_{sid}")
                            s_vat     = se3.text_input("VAT / NIF", value=full_s.get("vat",""), key=f"svat_{sid}")

                            se4, se5, se6 = st.columns(3)
                            s_country = se4.text_input("País", value=full_s.get("country",""), key=f"sco_{sid}")
                            s_type    = se5.selectbox("Tipo", SUPPLIER_TYPES,
                                index=SUPPLIER_TYPES.index(full_s.get("supplier_type","Fornecedor Direto")) if full_s.get("supplier_type") in SUPPLIER_TYPES else 0,
                                key=f"stype_{sid}")
                            s_status  = se6.selectbox("Status", SUPPLIER_STATUSES,
                                index=SUPPLIER_STATUSES.index(full_s.get("status","Ativo")) if full_s.get("status") in SUPPLIER_STATUSES else 0,
                                key=f"sstat_{sid}")

                            se7, se8 = st.columns(2)
                            s_brand   = se7.text_input("Marca Principal", value=full_s.get("brand",""), key=f"sbr_{sid}")
                            _cgf_ref  = CGF_REFERENCE.get((full_s.get("brand","") or "").upper())
                            _cgf_help = f"Referência Business Plan: {_cgf_ref}%" if _cgf_ref else ""
                            s_cgf     = se8.number_input("CGF / Rebate (%)", min_value=0.0, max_value=60.0,
                                step=0.1, format="%.3f",
                                value=float(full_s.get("cgf") or 0),
                                help=_cgf_help, key=f"scgf_{sid}")

                            se9, se10, se11 = st.columns(3)
                            s_inc     = se9.text_input("Incoterm", value=full_s.get("incoterm",""), key=f"sinc_{sid}")
                            s_pay     = se10.text_input("Condições Pagamento", value=full_s.get("payment_terms",""), key=f"spay_{sid}")
                            s_curr    = se11.selectbox("Moeda", ["EUR","USD","GBP","CHF"],
                                index=["EUR","USD","GBP","CHF"].index(full_s.get("currency","EUR")) if full_s.get("currency") in ["EUR","USD","GBP","CHF"] else 0,
                                key=f"scurr_{sid}")

                            se12, se13 = st.columns(2)
                            s_minord  = se12.number_input("Pedido Mínimo", min_value=0.0, step=100.0,
                                value=float(full_s.get("min_order") or 0), key=f"smo_{sid}")
                            s_lead    = se13.text_input("Lead Time", value=full_s.get("lead_time",""),
                                placeholder="Ex: 3–5 dias úteis", key=f"slt_{sid}")

                            s_brands  = st.multiselect("Marcas / Portfolio", SUP_BRANDS,
                                default=[b for b in (full_s.get("brands") or []) if b in SUP_BRANDS],
                                key=f"sbrs_{sid}")
                            s_cats    = st.multiselect("Categorias", SUP_CATS,
                                default=[c for c in (full_s.get("categories") or []) if c in SUP_CATS],
                                key=f"scats_{sid}")

                            s_notes   = st.text_area("Notas", value=full_s.get("notes",""),
                                height=70, key=f"snotes_{sid}")

                            if st.button("💾 Guardar Alterações", key=f"ssave_{sid}", type="primary"):
                                ok = update_supplier(sid, {
                                    "supplier_name": s_name,
                                    "legal_name":    s_legal,
                                    "vat":           s_vat,
                                    "country":       s_country,
                                    "supplier_type": s_type,
                                    "status":        s_status,
                                    "brand":         s_brand,
                                    "cgf":           s_cgf,
                                    "incoterm":      s_inc,
                                    "payment_terms": s_pay,
                                    "currency":      s_curr,
                                    "min_order":     s_minord,
                                    "lead_time":     s_lead,
                                    "brands":        s_brands,
                                    "categories":    s_cats,
                                    "notes":         s_notes,
                                })
                                if ok:
                                    st.success("✅ Fornecedor actualizado.")
                                    st.rerun()
                                else:
                                    st.error("Erro ao guardar.")

                    # ── Gestão de Contactos ─────────────────────────────────
                    with st.expander("👤 Contactos", expanded=False):
                        _scontacts = get_supplier_contacts(sid)

                        if _scontacts:
                            st.markdown("**Contactos registados**")
                            for _sci, _sct in enumerate(_scontacts):
                                _is_prim = _sct.get("primary", False)
                                _pbadge  = "🌟 **Principal**" if _is_prim else f"#{_sci + 1}"
                                with st.container():
                                    _scc1, _scc2 = st.columns([5, 1])
                                    with _scc1:
                                        st.markdown(
                                            f"{_pbadge} — **{_sct.get('name','—')}**  ·  "
                                            f"_{_sct.get('role','') or 'Sem cargo'}_  \n"
                                            f"📧 {_sct.get('email','—')}  ·  📱 {_sct.get('phone','—')}"
                                            + (f"  \n🔗 {_sct.get('linkedin','')}" if _sct.get("linkedin") else "")
                                        )
                                    with _scc2:
                                        _sb_cols = st.columns(2)
                                        if _sb_cols[1].button("🗑️", key=f"sdel_ct_{sid}_{_sci}",
                                                              help="Remover contacto"):
                                            _new_scts = [c for i, c in enumerate(_scontacts) if i != _sci]
                                            if save_supplier_contacts(sid, _new_scts):
                                                st.success("Contacto removido.")
                                                st.rerun()
                                        if not _is_prim:
                                            if _sb_cols[0].button("⭐", key=f"sprim_ct_{sid}_{_sci}",
                                                                   help="Definir como principal"):
                                                for _sx in _scontacts:
                                                    _sx["primary"] = False
                                                _scontacts[_sci]["primary"] = True
                                                if save_supplier_contacts(sid, _scontacts):
                                                    st.success("Contacto principal actualizado.")
                                                    st.rerun()

                                    with st.expander(f"✏️ Editar contacto #{_sci + 1}", expanded=False):
                                        _sec1, _sec2 = st.columns(2)
                                        _sct_name  = _sec1.text_input("Nome", value=_sct.get("name",""), key=f"sctn_{sid}_{_sci}")
                                        _sct_role  = _sec2.selectbox("Cargo / Função", [""] + SUP_ROLES,
                                            index=([""] + SUP_ROLES).index(_sct.get("role","")) if _sct.get("role") in SUP_ROLES else 0,
                                            key=f"sctr_{sid}_{_sci}")
                                        _sec3, _sec4 = st.columns(2)
                                        _sct_email = _sec3.text_input("Email", value=_sct.get("email",""), key=f"scte_{sid}_{_sci}")
                                        _sct_phone = _sec4.text_input("Telefone", value=_sct.get("phone",""), key=f"sctp_{sid}_{_sci}")
                                        _sct_link  = st.text_input("LinkedIn", value=_sct.get("linkedin",""), key=f"sctl_{sid}_{_sci}")
                                        _sct_notes = st.text_input("Notas", value=_sct.get("notes",""), key=f"sctno_{sid}_{_sci}")
                                        if st.button("💾 Guardar contacto", key=f"sctsave_{sid}_{_sci}"):
                                            _scontacts[_sci].update({
                                                "name": _sct_name, "role": _sct_role,
                                                "email": _sct_email, "phone": _sct_phone,
                                                "linkedin": _sct_link, "notes": _sct_notes,
                                            })
                                            if save_supplier_contacts(sid, _scontacts):
                                                st.success("✅ Contacto guardado.")
                                                st.rerun()
                                            else:
                                                st.error("Erro ao guardar.")
                                st.divider()
                        else:
                            st.info("Ainda não há contactos registados.")

                        st.markdown("**➕ Adicionar contacto**")
                        _sna1, _sna2 = st.columns(2)
                        _snct_name  = _sna1.text_input("Nome *", key=f"snct_name_{sid}")
                        _snct_role  = _sna2.selectbox("Cargo / Função", [""] + SUP_ROLES, key=f"snct_role_{sid}")
                        _sna3, _sna4 = st.columns(2)
                        _snct_email = _sna3.text_input("Email", key=f"snct_email_{sid}")
                        _snct_phone = _sna4.text_input("Telefone", key=f"snct_phone_{sid}")
                        _snct_link  = st.text_input("LinkedIn", key=f"snct_link_{sid}")
                        _snct_notes = st.text_input("Notas", key=f"snct_notes_{sid}")
                        _snct_prim  = st.checkbox("Definir como contacto principal",
                            key=f"snct_prim_{sid}", value=(len(_scontacts) == 0))

                        if st.button("➕ Adicionar Contacto", key=f"snct_add_{sid}"):
                            if not _snct_name.strip():
                                st.warning("O nome do contacto é obrigatório.")
                            else:
                                _new_sct = {
                                    "name": _snct_name.strip(), "role": _snct_role,
                                    "email": _snct_email.strip(), "phone": _snct_phone.strip(),
                                    "linkedin": _snct_link.strip(), "notes": _snct_notes.strip(),
                                    "primary": _snct_prim,
                                }
                                if _snct_prim:
                                    for _xsc in _scontacts:
                                        _xsc["primary"] = False
                                _scontacts.append(_new_sct)
                                if save_supplier_contacts(sid, _scontacts):
                                    st.success("✅ Contacto adicionado.")
                                    st.rerun()
                                else:
                                    st.error("Erro ao guardar.")

                    # ── Deals Vinculados ────────────────────────────────────
                    with st.expander("📦 Deals Vinculados a este Fornecedor", expanded=False):
                        _sup_deals = get_supplier_deals(sname, sbrand)
                        if not _sup_deals:
                            st.info("Sem deals com este fornecedor registados ainda.  \n"
                                    "_Associa fornecedores aos deals em 'Deals em Curso → Dados Operacionais'_")
                        else:
                            # Separar em aberto vs fechado
                            from config import PIPELINE_CLOSED_STATUSES as _PCS
                            _sd_active = [d for d in _sup_deals if d.get("status") not in _PCS]
                            _sd_closed = [d for d in _sup_deals if d.get("status") in _PCS]

                            if _sd_active:
                                st.markdown(f"**🟢 Em Curso ({len(_sd_active)})**")
                                for _sd in _sd_active:
                                    _sd_c1, _sd_c2, _sd_c3, _sd_c4 = st.columns([2, 2, 2, 2])
                                    _sd_c1.markdown(f"**{_sd.get('deal_id','-')}** — {_sd.get('client','-')}")
                                    _sd_c2.markdown(f"{STATUS_EMOJI.get(_sd.get('status',''),'')}"
                                                    f" {_sd.get('status','—')}")
                                    _sd_c3.markdown(f"Entrega: **{_sd.get('expected_delivery','—') or '—'}**")
                                    _sd_c4.markdown(fmt2(_sd.get('proposed_value')))
                                st.divider()

                            if _sd_closed:
                                st.markdown(f"**✅ Fechados / Faturados ({len(_sd_closed)})**")
                                _sd_rows = []
                                for _sd in _sd_closed[:10]:
                                    _sd_rows.append({
                                        "Deal ID":    _sd.get("deal_id",""),
                                        "Cliente":    _sd.get("client",""),
                                        "Status":     _sd.get("status",""),
                                        "Valor (€)":  _sd.get("invoice_value") or _sd.get("proposed_value") or "",
                                        "Nº Fatura":  _sd.get("invoice_number","") or "—",
                                    })
                                if _sd_rows:
                                    st.dataframe(pd.DataFrame(_sd_rows), use_container_width=True, hide_index=True)

                    # ── Ações rápidas ───────────────────────────────────────
                    st.markdown("---")
                    _act1, _act2 = st.columns(2)
                    if _role in ("owner",) and _act2.button(
                        "🗑️ Apagar Fornecedor", key=f"sdel_{sid}",
                        type="secondary"
                    ):
                        if st.session_state.get(f"sdel_confirm_{sid}"):
                            if delete_supplier(sid):
                                st.success("Fornecedor apagado.")
                                st.session_state.pop(f"sdel_confirm_{sid}", None)
                                st.rerun()
                        else:
                            st.session_state[f"sdel_confirm_{sid}"] = True
                            st.warning("⚠️ Clica novamente para confirmar.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — NOVO FORNECEDOR
    # ══════════════════════════════════════════════════════════════════════════
    with tab_new:
        st.subheader("Novo Fornecedor")

        sn1, sn2, sn3 = st.columns(3)
        ns_name   = sn1.text_input("Nome Fornecedor *", key="ns_name")
        ns_legal  = sn2.text_input("Nome Legal / Faturação", key="ns_legal")
        ns_vat    = sn3.text_input("VAT / NIF", key="ns_vat")

        sn4, sn5, sn6 = st.columns(3)
        ns_country = sn4.text_input("País *", key="ns_country")
        ns_type    = sn5.selectbox("Tipo de Fornecedor", SUPPLIER_TYPES, key="ns_type")
        ns_status  = sn6.selectbox("Status", SUPPLIER_STATUSES, key="ns_status")

        st.markdown("**Marca & CGF**")
        sb1, sb2, sb3 = st.columns(3)
        ns_brand   = sb1.text_input("Marca Principal", key="ns_brand",
                                    placeholder="Ex: PHILIPS")
        _ns_ref    = CGF_REFERENCE.get((ns_brand or "").strip().upper())
        _ns_hint   = f"Referência: {_ns_ref}%" if _ns_ref else "CGF = % rebate do fornecedor"
        ns_cgf     = sb2.number_input("CGF / Rebate (%)", min_value=0.0, max_value=60.0,
                                      step=0.1, format="%.3f",
                                      value=float(_ns_ref or 0), help=_ns_hint, key="ns_cgf")
        ns_curr    = sb3.selectbox("Moeda", ["EUR","USD","GBP","CHF"], key="ns_curr")

        st.markdown("**Contacto Principal**")
        sc1, sc2, sc3, sc4 = st.columns(4)
        ns_cname   = sc1.text_input("Nome", key="ns_cname")
        ns_crole   = sc2.selectbox("Cargo", [""] + SUP_ROLES, key="ns_crole")
        ns_cemail  = sc3.text_input("Email *", key="ns_cemail")
        ns_cphone  = sc4.text_input("Telefone", key="ns_cphone")
        ns_clinked = st.text_input("LinkedIn", key="ns_clinked")

        st.markdown("**Condições Comerciais**")
        sc5, sc6, sc7 = st.columns(3)
        ns_inc     = sc5.text_input("Incoterm", placeholder="Ex: DDP", key="ns_inc")
        ns_pay     = sc6.text_input("Condições Pagamento", placeholder="Ex: 60 dias", key="ns_pay")
        ns_lead    = sc7.text_input("Lead Time", placeholder="Ex: 5–10 dias", key="ns_lead")
        ns_minord  = st.number_input("Pedido Mínimo (€)", min_value=0.0, step=100.0, key="ns_minord")

        st.markdown("**Portfolio**")
        ns_brands  = st.multiselect("Marcas / Portfolio", SUP_BRANDS, key="ns_brands")
        ns_cats    = st.multiselect("Categorias", SUP_CATS, key="ns_cats")
        ns_notes   = st.text_area("Notas", height=80, key="ns_notes")

        # Verificação de duplicados
        if ns_cemail or ns_name or ns_brand:
            _ns_dups = find_duplicate_suppliers(
                email=ns_cemail, supplier_name=ns_name, brand=ns_brand
            )
            if _ns_dups:
                st.warning(
                    "⚠️ **Possíveis duplicados encontrados:**  \n"
                    + "\n".join(
                        f"- **{d.get('supplier_name','—')}** · {d.get('brand','—')} "
                        f"· {d.get('contact_email','—')} · {d.get('status','—')}"
                        for d in _ns_dups[:4]
                    )
                )

        if st.button("➕ Criar Fornecedor", type="primary", key="btn_ns"):
            if not ns_name.strip():
                st.error("O nome do fornecedor é obrigatório.")
            else:
                new_sid = add_supplier({
                    "supplier_name":  ns_name.strip(),
                    "legal_name":     ns_legal,
                    "vat":            ns_vat,
                    "country":        ns_country,
                    "supplier_type":  ns_type,
                    "status":         ns_status,
                    "brand":          ns_brand,
                    "cgf":            ns_cgf,
                    "currency":       ns_curr,
                    "contact_name":   ns_cname,
                    "contact_role":   ns_crole,
                    "contact_email":  ns_cemail,
                    "contact_phone":  ns_cphone,
                    "contact_linkedin": ns_clinked,
                    "incoterm":       ns_inc,
                    "payment_terms":  ns_pay,
                    "lead_time":      ns_lead,
                    "min_order":      ns_minord,
                    "brands":         ns_brands,
                    "categories":     ns_cats,
                    "notes":          ns_notes,
                })
                if new_sid:
                    st.success(f"✅ Fornecedor **{ns_name}** criado (ID: {new_sid}).")
                    st.rerun()
                else:
                    st.error("Erro ao criar fornecedor.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — PERFORMANCE & CGF
    # ══════════════════════════════════════════════════════════════════════════
    with tab_cgf:
        st.subheader("📊 Performance de Fornecedores & CGF")
        st.caption(
            "Estimativa de rebate CGF por fornecedor com base nos deals registados. "
            "Requer que os deals tenham o campo **Fornecedor(es)** preenchido."
        )

        if st.button("🔄 Calcular CGF Dashboard", key="btn_cgf_dash", type="primary"):
            with st.spinner("A calcular..."):
                st.session_state["cgf_dashboard"] = get_cgf_dashboard_data()

        _cgf_dash = st.session_state.get("cgf_dashboard")
        if _cgf_dash is None:
            st.info("Clica em **Calcular CGF Dashboard** para gerar o relatório.")
        elif not _cgf_dash:
            st.warning("Sem fornecedores com CGF definido ou sem deals associados.")
        else:
            # ── KPIs globais ─────────────────────────────────────────────
            _total_planned = sum(r["planned_rebate"] for r in _cgf_dash)
            _total_closed  = sum(r["closed_rebate"]  for r in _cgf_dash)
            _total_active  = sum(r["active_value"]   for r in _cgf_dash)
            _total_forn    = len(_cgf_dash)

            _ck1, _ck2, _ck3, _ck4 = st.columns(4)
            _ck1.metric("Fornecedores c/ CGF", _total_forn)
            _ck2.metric("💰 Rebate Estimado Total", f"{_total_planned:,.2f} €")
            _ck3.metric("✅ Rebate s/ Deals Fechados", f"{_total_closed:,.2f} €")
            _ck4.metric("📦 Pipeline Ativo (valor)", f"{_total_active:,.0f} €")

            st.divider()

            # ── Tabela detalhada ──────────────────────────────────────────
            _cgf_rows = []
            for r in _cgf_dash:
                _cgf_rows.append({
                    "Fornecedor":         r["supplier"],
                    "Marca":              r["brand"],
                    "CGF %":              f"{r['cgf_pct']:.2f}%",
                    "Deals Activos":      r["active_deals"],
                    "Valor Activo (€)":   f"{r['active_value']:,.2f}",
                    "Deals Fechados":     r["closed_deals"],
                    "Valor Fechado (€)":  f"{r['closed_value']:,.2f}",
                    "Rebate Estimado (€)":f"{r['planned_rebate']:,.2f}",
                    "Rebate Fechado (€)": f"{r['closed_rebate']:,.2f}",
                })
            st.dataframe(pd.DataFrame(_cgf_rows), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🔔 Encomendas em Curso com Entrega Próxima")
            st.caption("Deals em status de processamento (Encomenda Confirmada, Em Preparação, Expedido) com entrega prevista definida.")

            from config import PIPELINE_ORDER_STATUSES as _POS
            _order_deals = []
            try:
                from deal_tracker import _get_client as _dt_client
                _od_res = (_dt_client().table("deals")
                           .select("deal_id,client,status,expected_delivery,supplier_ids,proposed_value")
                           .in_("status", _POS)
                           .not_.is_("expected_delivery", "null")
                           .order("expected_delivery")
                           .execute())
                _order_deals = _od_res.data or []
            except Exception as _oe:
                st.warning(f"Erro ao carregar encomendas: {_oe}")

            if not _order_deals:
                st.info("Sem encomendas em processamento com data de entrega definida.")
            else:
                from datetime import datetime as _dt_now
                _today = _dt_now.now()
                _od_rows = []
                for _od in _order_deals:
                    _exp = _od.get("expected_delivery","") or ""
                    _days_left = None
                    try:
                        _exp_dt    = _dt_now.strptime(_exp[:10], "%Y-%m-%d")
                        _days_left = (_exp_dt - _today).days
                    except Exception:
                        pass
                    _alert = ""
                    if _days_left is not None:
                        if _days_left < 0:    _alert = "⚠️ ATRASADO"
                        elif _days_left <= 3: _alert = "🔴 Urgente"
                        elif _days_left <= 7: _alert = "🟡 Esta semana"
                        else:                 _alert = "🟢 OK"
                    _od_rows.append({
                        "Deal":            _od.get("deal_id",""),
                        "Cliente":         _od.get("client",""),
                        "Status":          _od.get("status",""),
                        "Entrega Prevista":_exp[:10] if _exp else "—",
                        "Dias Restantes":  _days_left if _days_left is not None else "—",
                        "Alerta":          _alert,
                        "Fornecedor(es)":  _od.get("supplier_ids","") or "—",
                        "Valor (€)":       f"{float(_od.get('proposed_value') or 0):,.2f}",
                    })
                st.dataframe(pd.DataFrame(_od_rows), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — QUALIDADE DE DADOS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_quality:
        st.subheader("🔍 Qualidade de Dados — Fornecedores")

        _sq_col1, _sq_col2 = st.columns(2)
        if _sq_col1.button("🔄 Analisar Base de Dados", key="btn_sup_qa", type="primary"):
            with st.spinner("A analisar..."):
                st.session_state["sup_qa_report"] = supplier_quality_report()

        if _sq_col2.button("⚡ Auto-preencher CGF (referências BP)", key="btn_auto_cgf"):
            with st.spinner("A preencher CGF..."):
                _cgf_r = auto_fill_cgf_from_reference()
            st.success(f"✅ CGF preenchido: **{_cgf_r['updated']}** actualizados  ·  {_cgf_r['skipped']} sem match")
            st.session_state.pop("sup_qa_report", None)

        if "sup_qa_report" not in st.session_state:
            st.info("Clica em **Analisar Base de Dados** para ver o relatório.")
        else:
            _sq = st.session_state["sup_qa_report"]

            # Métricas
            _qm1, _qm2, _qm3, _qm4 = st.columns(4)
            _qm1.metric("Total Fornecedores", _sq["total"])
            _qm2.metric("Telefones sem código", len(_sq["phone_issues"]))
            _qm3.metric("Possíveis duplicados", len(_sq["duplicates"]))
            _qm4.metric("Sem CGF definido", len(_sq["no_cgf"]))

            st.divider()

            # ── Sem CGF ──────────────────────────────────────────────────────
            with st.expander(f"💰 Fornecedores sem CGF ({len(_sq['no_cgf'])})", expanded=True):
                if not _sq["no_cgf"]:
                    st.success("✅ Todos os fornecedores têm CGF definido.")
                else:
                    for nc in _sq["no_cgf"]:
                        _ref = CGF_REFERENCE.get((nc.get("brand","") or "").upper())
                        _ref_txt = f" — referência Business Plan: **{_ref}%**" if _ref else ""
                        st.warning(f"**{nc['supplier']}** · Marca: {nc.get('brand','—')}{_ref_txt}")
                    st.caption("Usa o botão **Auto-preencher CGF** ou edita manualmente.")

            # ── Telefones ────────────────────────────────────────────────────
            with st.expander(f"📱 Telefones sem indicativo ({len(_sq['phone_issues'])})", expanded=False):
                if not _sq["phone_issues"]:
                    st.success("✅ Todos os telefones têm indicativo de país.")
                else:
                    for pi in _sq["phone_issues"]:
                        _pc1, _pc2 = st.columns([4, 1])
                        _pc1.markdown(
                            f"**{pi['supplier']}** — {pi['contact']}  \n"
                            f"📱 `{pi['phone']}` · {pi['country']}"
                            + (f"  → sugestão: `{pi['suggested']}`" if pi['suggested'] else "")
                        )
                        if pi["suggested"] and _pc2.button("Corrigir", key=f"sqfix_{pi['id']}"):
                            from client_tracker import COUNTRY_PHONE_CODES
                            _ph_clean = pi["phone"].lstrip("0").strip()
                            update_supplier(str(pi["id"]), {
                                "contact_phone": f"{pi['suggested']} {_ph_clean}"
                            })
                            st.success("✅ Telefone corrigido.")
                            st.session_state.pop("sup_qa_report", None)
                            st.rerun()

            # ── Duplicados ───────────────────────────────────────────────────
            with st.expander(f"🔁 Possíveis duplicados ({len(_sq['duplicates'])})", expanded=False):
                if not _sq["duplicates"]:
                    st.success("✅ Sem duplicados detectados.")
                else:
                    for grp in _sq["duplicates"]:
                        names = " / ".join(s.get("supplier_name","—") for s in grp)
                        st.warning(f"Grupo similar: **{names}**")
                        _g_cols = st.columns(len(grp))
                        for gi, (gc, gcol) in enumerate(zip(grp, _g_cols)):
                            gcol.markdown(
                                f"**{gc.get('supplier_name','—')}**  \n"
                                f"{gc.get('brand','—')}  \n"
                                f"`{gc.get('contact_email','—')}`  \n"
                                f"{gc.get('country','—')} · {gc.get('status','—')}"
                            )
                        ids    = [str(s["id"]) for s in grp]
                        labels = [s.get("supplier_name","—") for s in grp]
                        mg1, mg2, mg3 = st.columns([2, 2, 1])
                        _sprim = mg1.selectbox("Manter (primary)", options=ids,
                            format_func=lambda x: labels[ids.index(x)],
                            key=f"smg_prim_{ids[0]}")
                        _ssec  = mg2.selectbox("Apagar (secondary)", options=ids,
                            format_func=lambda x: labels[ids.index(x)],
                            key=f"smg_sec_{ids[0]}", index=1 if len(ids) > 1 else 0)
                        if mg3.button("🔀 Merge", key=f"smg_btn_{ids[0]}"):
                            if _sprim == _ssec:
                                st.error("Primary e secondary têm de ser diferentes.")
                            else:
                                ok = merge_suppliers(_sprim, _ssec)
                                if ok:
                                    st.success("✅ Merge concluído.")
                                    st.session_state.pop("sup_qa_report", None)
                                    st.rerun()
                                else:
                                    st.error("Erro no merge.")
                        st.divider()

            # ── Campos em falta ──────────────────────────────────────────────
            with st.expander(f"📋 Campos importantes em falta ({len(_sq['missing_fields'])})",
                             expanded=False):
                if not _sq["missing_fields"]:
                    st.success("✅ Sem campos obrigatórios em falta.")
                else:
                    _sq_df = pd.DataFrame([
                        {"Fornecedor": r["supplier"], "Campos em Falta": ", ".join(r["missing"])}
                        for r in _sq["missing_fields"]
                    ])
                    st.dataframe(_sq_df, use_container_width=True, hide_index=True)

            # ── Tabela CGF de referência ─────────────────────────────────────
            with st.expander("💡 Tabela de referência CGF (Business Plan)", expanded=False):
                _cgf_rows = [{"Marca": b, "CGF %": f"{v:.1f}%"} for b, v in
                             sorted(CGF_REFERENCE.items(), key=lambda x: -x[1])]
                st.dataframe(pd.DataFrame(_cgf_rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA — LOGÍSTICA
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🚚  Logística":
    import pandas as pd
    st.title("🚚 Simulador Logístico — Comparador de Tarifas")
    st.caption("Compara tarifas de 6 transportadoras para envios B2B a partir de Azambuja.")

    _tc = load_transport()

    _lt_tab1, _lt_tab2 = st.tabs(["📦 Comparador de Tarifas", "🔄 Actualizar Cache"])

    with _lt_tab1:
        if not _tc or not _tc.get("destinations"):
            st.warning("Cache de tarifas não encontrado. Vai ao tab **Actualizar Cache** e clica em **Reconstruir**.")
        else:
            _lt_countries = get_countries(_tc)
            if not _lt_countries:
                st.error("Sem países disponíveis no cache.")
            else:
                _lc1, _lc2, _lc3, _lc4 = st.columns([2, 1.5, 1, 1.5])
                _lt_country = _lc1.selectbox("🌍 País de destino", _lt_countries, key="lt_country")
                _lt_cps     = get_cps_for_country(_lt_country, _tc)
                _lt_cp      = _lc2.selectbox("📮 Zona Postal (CP)", _lt_cps, key="lt_cp") if _lt_cps else None
                _lt_pallets = _lc3.number_input("📦 Nº Paletes", min_value=1, max_value=33, value=1, step=1, key="lt_pallets")
                _lt_cargo   = _lc4.number_input("💶 Valor da Carga (€)", min_value=0.0, step=100.0, value=0.0, key="lt_cargo",
                                                  help="Necessário para cálculo do seguro")

                _lt_ins = st.checkbox("➕ Incluir seguro no total", value=False, key="lt_ins")

                if _lt_cp and st.button("🔍 Comparar Tarifas", key="lt_search", type="primary"):
                    _c_cp = f"{_lt_country}{_lt_cp}"
                    _quotes = get_quote(
                        c_cp              = _c_cp,
                        n_pallets         = int(_lt_pallets),
                        cargo_value       = float(_lt_cargo),
                        include_insurance = _lt_ins,
                        cache             = _tc,
                    )
                    st.session_state["lt_quotes"]      = _quotes
                    st.session_state["lt_c_cp"]        = _c_cp
                    st.session_state["lt_pallets"]     = int(_lt_pallets)
                    st.session_state["lt_country_sel"] = _lt_country

                _quotes = st.session_state.get("lt_quotes")
                if _quotes is not None:
                    _c_cp_disp = st.session_state.get("lt_c_cp", "")
                    _np_disp   = st.session_state.get("lt_pallets", 1)
                    _ctry_disp = st.session_state.get("lt_country_sel", "")

                    st.divider()
                    st.subheader(f"Resultados — {_ctry_disp} (zona {_c_cp_disp.replace(_ctry_disp,'')}) · {_np_disp} paletes")

                    if not _quotes:
                        st.warning("Sem cotações disponíveis para este destino/nº de paletes.")
                    else:
                        # Best price and best TT
                        _best_price_carrier = _quotes[0]["carrier"]
                        _tt_available = [q for q in _quotes if q.get("tt_days")]
                        _best_tt_carrier = min(_tt_available, key=lambda x: x["tt_days"])["carrier"] if _tt_available else None

                        # Display cards
                        _q_cols = st.columns(min(len(_quotes), 3))
                        for _qi, _q in enumerate(_quotes):
                            _col = _q_cols[_qi % 3]
                            _badges = []
                            if _q["carrier"] == _best_price_carrier:
                                _badges.append("🏆 Mais Barato")
                            if _q["carrier"] == _best_tt_carrier:
                                _badges.append("⚡ Mais Rápido")
                            _badge_str = "  ".join(_badges)
                            _border_color = "#1F4E79" if _badges else "#ddd"
                            _bg_color = "#E8F0FE" if _badges else "white"
                            _badge_html = (
                                "<br><small style=\"color:#1F4E79\"><b>" + _badge_str + "</b></small>"
                                if _badges else ""
                            )

                            with _col:
                                st.markdown(
                                    "<div style='border:1px solid " + _border_color + ";border-radius:8px;"
                                    "padding:12px;margin:4px 0;background:" + _bg_color + "'>"
                                    "<b style='font-size:16px'>" + _q["carrier"] + "</b>"
                                    + _badge_html +
                                    "<hr style='margin:6px 0'>"
                                    "<b>Frete base:</b> " + f"{_q['freight']:,.2f}" + " €<br>"
                                    "<b>Fuel surcharge:</b> " + f"{_q['fuel']:,.2f}" + " €<br>"
                                    "<b>Seguro:</b> " + (_q["ins_label"] or "—") + "<br>"
                                    "<b>TOTAL: " + f"{_q['total']:,.2f}" + " €</b><br>"
                                    "<hr style='margin:6px 0'>"
                                    "<b>Trânsito:</b> " + (str(_q["tt_days"]) + " dias" if _q["tt_days"] else "—") + "<br>"
                                    "<b>Partidas:</b> " + (_q["departure"] or "—") +
                                    "</div>",
                                    unsafe_allow_html=True,
                                )

                        st.divider()

                        # Full comparison table
                        _tbl_rows = []
                        for _q in _quotes:
                            _tbl_rows.append({
                                "Transportadora":  _q["carrier"],
                                "Frete (€)":       f"{_q['freight']:,.2f}",
                                "Fuel (€)":        f"{_q['fuel']:,.2f}",
                                "Seguro":          _q["ins_label"] or "—",
                                "TOTAL (€)":       f"{_q['total']:,.2f}",
                                "Trânsito (dias)": _q["tt_days"] or "—",
                                "Partidas":        _q["departure"] or "—",
                            })
                        st.dataframe(pd.DataFrame(_tbl_rows), use_container_width=True, hide_index=True)

                        # Associar ao deal
                        st.divider()
                        st.markdown("**📋 Associar cotação a um Deal**")
                        _sp_filter_lt = _cu.get("email") if _role in OWN_DATA_ONLY else None
                        _lt_deals = list_deals(salesperson_filter=_sp_filter_lt)
                        _lt_active = [d for d in _lt_deals
                                      if d.get("Status", "") not in ("Perdido", "Arquivado", "Faturado")]
                        if not _lt_active:
                            st.info("Sem deals ativos para associar.")
                        else:
                            _lt_deal_opts = {
                                f"{d.get('Deal ID','')} — {d.get('Cliente','')} ({d.get('País','')})": d.get("Deal ID", "")
                                for d in reversed(_lt_active)
                            }
                            _lt_deal_sel = st.selectbox("Selecionar Deal", list(_lt_deal_opts.keys()), key="lt_deal_sel")
                            _lt_carrier_sel = st.selectbox(
                                "Transportadora escolhida",
                                [_q["carrier"] for _q in _quotes],
                                key="lt_carrier_sel",
                            )
                            _chosen_q = next((q for q in _quotes if q["carrier"] == _lt_carrier_sel), None)
                            if _chosen_q:
                                _lt_freight_chosen = st.number_input(
                                    "Frete a usar no deal (€)",
                                    min_value=0.0, step=0.01,
                                    value=float(_chosen_q["total"]),
                                    key="lt_freight_chosen",
                                )
                                if st.button("💾 Associar ao Deal", key="lt_assoc", type="primary"):
                                    _lt_did = _lt_deal_opts[_lt_deal_sel]
                                    _ok = update_deal_operational(
                                        _lt_did,
                                        supplier_ids=_lt_carrier_sel,
                                    )
                                    _lt_current_status = next(
                                        (d.get("Status", "Rascunho") for d in _lt_active if d.get("Deal ID") == _lt_did),
                                        "Rascunho",
                                    )
                                    update_status(
                                        _lt_did,
                                        _lt_current_status,
                                        f"Transportadora: {_lt_carrier_sel} · Frete: {_lt_freight_chosen:.2f} €",
                                    )
                                    if _ok:
                                        st.success(f"Transportadora **{_lt_carrier_sel}** ({_lt_freight_chosen:.2f} €) associada ao deal **{_lt_did}**.")
                                    else:
                                        st.error("Erro ao associar.")

                        # ── Pedido de cotação à transportadora ─────────────
                        st.divider()
                        st.markdown("**📧 Pedir Cotação à Transportadora**")
                        _tr_carrier_email = st.text_input(
                            "Email da transportadora",
                            placeholder="Ex: quotes@dsv.com",
                            key="lt_carrier_email",
                        )
                        _tr_collection = st.text_input(
                            "Data prevista de recolha",
                            placeholder="Ex: 15/04/2026",
                            key="lt_collection_date",
                        )
                        _tr_deal_for_req = st.selectbox(
                            "Deal de referência (opcional)",
                            ["— Sem deal associado —"] + list(_lt_deal_opts.keys()),
                            key="lt_req_deal",
                        )
                        if st.button("📧 Gerar Pedido de Cotação", key="lt_gen_req", type="secondary"):
                            _tr_deal_obj = {}
                            if _tr_deal_for_req != "— Sem deal associado —":
                                _tr_did = _lt_deal_opts[_tr_deal_for_req]
                                _tr_deal_obj = get_deal(_tr_did) or {}
                            # Build minimal deal dict if no deal selected
                            if not _tr_deal_obj:
                                _tr_deal_obj = {
                                    "Deal ID": "—",
                                    "Cliente": "—",
                                    "País": st.session_state.get("lt_country_sel",""),
                                    "Incoterm": "EXW — Ex Works (Azambuja)",
                                    "_skus_detail": {},
                                }
                            with st.spinner("A gerar..."):
                                try:
                                    _tr_html = generate_transport_request(
                                        deal           = _tr_deal_obj,
                                        carrier_name   = st.session_state.get("lt_carrier_sel",""),
                                        carrier_email  = _tr_carrier_email,
                                        n_pallets      = int(st.session_state.get("lt_pallets", 1)),
                                        cargo_value    = float(st.session_state.get("lt_cargo", 0)),
                                        collection_date= _tr_collection,
                                    )
                                    st.session_state["lt_transport_req_html"] = _tr_html
                                except Exception as _e:
                                    st.error(f"Erro: {_e}")

                        if st.session_state.get("lt_transport_req_html"):
                            _tq_html = st.session_state["lt_transport_req_html"]
                            with st.expander("👁️ Pré-visualizar pedido", expanded=True):
                                st.components.v1.html(_tq_html, height=450, scrolling=True)
                            _tr_send_to = st.text_input(
                                "Enviar para (transportadora)",
                                value=st.session_state.get("lt_carrier_email",""),
                                key="lt_req_send_to",
                            )
                            _tr_send_cc = st.text_input("CC", value="", key="lt_req_cc",
                                                         help="Separa múltiplos com ;")
                            if st.button("🚀 Enviar Pedido", key="lt_req_send", type="primary"):
                                if _tr_send_to:
                                    _tr_subj = f"Pedido de Cotação de Transporte — {st.session_state.get('lt_c_cp','')}"
                                    _tr_cc_list = [e.strip() for e in _tr_send_cc.split(";") if e.strip()] or None
                                    _tr_ok, _tr_err = create_draft(_tr_send_to, _tr_subj, _tq_html, send=True, cc=_tr_cc_list)
                                    if _tr_ok:
                                        st.success("✅ Pedido de cotação enviado!")
                                        st.session_state.pop("lt_transport_req_html", None)
                                    else:
                                        st.error(f"Erro: {_tr_err}")
                                else:
                                    st.warning("Indica o email da transportadora.")

    with _lt_tab2:
        st.subheader("🔄 Actualizar Cache de Tarifas")

        if _tc and _tc.get("destinations"):
            _n_dest = len(_tc.get("destinations", {}))
            st.success(f"✅ Cache activo — **{_n_dest}** destinos · {len(_tc.get('countries', []))} países")
        else:
            st.warning("⚠️ Cache não disponível — simulador desactivado neste ambiente.")

        from config import TRANSPORT_FILE as _TF
        if _TF.exists():
            st.info(f"Ficheiro de tarifas encontrado: `{_TF.name}`")
            if st.button("🔨 Reconstruir Cache de Tarifas", key="lt_rebuild", type="primary"):
                with st.spinner("A ler Excel e reconstruir cache..."):
                    try:
                        _new_cache = build_transport_cache()
                        st.cache_data.clear()
                        _nd2 = len(_new_cache.get("destinations", {}))
                        st.success(
                            f"✅ Cache reconstruído — **{_nd2}** destinos · "
                            f"{len(_new_cache.get('countries', []))} países"
                        )
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Erro ao reconstruir: {_e}")
                        import traceback; st.code(traceback.format_exc())
        else:
            st.error(
                "❌ **Ficheiro Excel de tarifas não encontrado neste servidor.**\n\n"
                "O simulador logístico funciona apenas em ambiente local onde o ficheiro "
                "`Simulador_Exportacao_V2.26 - B2B.xlsx` está disponível.\n\n"
                "**Para activar no cloud:** constrói o cache localmente e faz commit do ficheiro "
                "`.cache/transport_cache.json` para o repositório."
            )
            st.markdown("**Comando para correr localmente:**")
            st.code(
                "cd cotacao_agent\n"
                "py -3 -c \"from transport_lookup import build_transport_cache; "
                "build_transport_cache(); print('Cache construído com sucesso')\"\n"
                "git add .cache/transport_cache.json\n"
                "git commit -m 'feat: add pre-built transport cache'\n"
                "git push",
                language="bash"
            )


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 4 — PESQUISAR PRODUTO
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍  Pesquisar Produto":
    st.title("🔍 Pesquisar Produto no Simulador")
    tab_nome, tab_ean = st.tabs(["🔤 Por Nome / Marca","📊 Por EAN"])

    with tab_nome:
        q = st.text_input("Nome / marca", placeholder="Ex: Philips Airfryer, Samsung...")
        if q and len(q) >= 3:
            with st.spinner("A pesquisar..."):
                res = search_by_name(q, max_results=20)
            if not res:
                st.warning("Sem resultados.")
            else:
                st.success(f"{len(res)} resultado(s)")
                hh = st.columns([1.2,1.6,3,1.5,1.5,1.5,1.2])
                for col,lbl in zip(hh,["SKU","EAN","Produto","FC Simulador","PVP PT","EIS DA","Sell-In"]):
                    col.caption(lbl)
                st.markdown("---")
                for r in res:
                    uc = r.get("ufc_raw"); eis_da = r.get("eis_da") or 0; si = r.get("sell_in")
                    cc = st.columns([1.2,1.6,3,1.5,1.5,1.5,1.2])
                    cc[0].markdown(f"**`{r['sku_id']}`**")
                    cc[1].markdown(f"`{r.get('ean','—')}`")
                    cc[2].markdown(f"{r.get('brand','—')} · {r.get('name','')[:48]}")
                    cc[3].markdown(fmt4(uc) if uc else "⚠️ N/D")
                    cc[4].markdown(fmt4(r.get("pvp_pt")))
                    cc[5].markdown(f"{'⚠️ ' if eis_da>0 else '—'}{fmt4(eis_da) if eis_da>0 else ''}")
                    cc[6].markdown(f"{'✅' if si else '—'}")
        elif q:
            st.caption("Insere pelo menos 3 caracteres.")

    with tab_ean:
        eq = st.text_input("Código EAN", placeholder="Ex: 5908099018610")
        if eq and len(eq) >= 8:
            with st.spinner("A pesquisar por EAN..."):
                idx = load_index()
                r   = next((v for v in idx.values() if v.get("ean","").strip()==eq.strip()), None)
            if not r:
                st.warning(f"EAN **{eq}** não encontrado.")
            else:
                st.success(f"✅ SKU: **{r['sku_id']}**")
                c1,c2,c3 = st.columns(3)
                c1.markdown(f"**SKU:** `{r['sku_id']}`")
                c2.markdown(f"**EAN:** `{r.get('ean','—')}`")
                c3.markdown(f"**Marca:** {r.get('brand','—')}")
                st.markdown(f"**Produto:** {r.get('name','—')}")
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("UFC Raw", fmt4(r.get("ufc_raw")) if r.get("ufc_raw") else "N/D")
                m2.metric("PVP Portugal", fmt4(r.get("pvp_pt")) if r.get("pvp_pt") else "N/D")
                m3.metric("EIS Dir. Autor", fmt4(r.get("eis_da")) if r.get("eis_da") else "—")
                m4.metric("Sell-In", fmt4(r.get("sell_in")) if r.get("sell_in") else "—")
                st.info(f"💡 Usa o SKU **{r['sku_id']}** na página **Nova Cotação**.")
        elif eq:
            st.caption("Insere pelo menos 8 dígitos.")


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA ADMIN — Gestão de Utilizadores (Owner only)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️  Administração":
    if _role != "owner":
        st.error("Acesso restrito.")
        st.stop()

    st.title("⚙️ Administração — Utilizadores")

    tab_users, tab_new_user = st.tabs(["👤 Utilizadores", "➕ Novo Utilizador"])

    with tab_users:
        users = list_users()
        st.caption(f"{len(users)} utilizador(es)")
        for u in users:
            uid    = str(u.get("id",""))
            uname  = u.get("name","—")
            uemail = u.get("email","—")
            urole  = u.get("role","—")
            uact   = u.get("is_active", True)
            ulast  = u.get("last_login","—") or "Nunca"

            _badge = ROLE_BADGE_COLOR.get(urole,"#333")
            with st.expander(
                f"{'🟢' if uact else '⚫'} **{uname}** — {uemail}  ·  "
                f"{ROLE_LABELS.get(urole,urole)}  ·  Último login: {ulast}"
            ):
                ua1, ua2, ua3 = st.columns(3)
                new_name  = ua1.text_input("Nome", value=uname, key=f"un_{uid}")
                new_role  = ua2.selectbox("Perfil", ROLES,
                    index=ROLES.index(urole) if urole in ROLES else 0,
                    format_func=lambda r: ROLE_LABELS.get(r,r),
                    key=f"ur_{uid}")
                new_active = ua3.checkbox("Ativo", value=uact, key=f"ua_{uid}")

                if st.button("💾 Guardar", key=f"usave_{uid}"):
                    ok = update_user(uid, {
                        "name": new_name, "role": new_role, "is_active": new_active
                    })
                    st.success("✅ Guardado.") if ok else st.error("Erro.")
                    st.rerun()

                st.markdown("---")
                st.markdown("**Reset de Password**")
                rp1, rp2, rp3 = st.columns(3)
                new_pwd  = rp1.text_input("Nova password", type="password", key=f"np_{uid}")
                new_pwd2 = rp2.text_input("Confirmar", type="password", key=f"np2_{uid}")
                rp3.markdown("<br>", unsafe_allow_html=True)
                if rp3.button("🔑 Reset", key=f"rp_{uid}"):
                    if not new_pwd:
                        st.error("Introduz a nova password.")
                    elif new_pwd != new_pwd2:
                        st.error("As passwords não coincidem.")
                    else:
                        ok = reset_password(uid, new_pwd)
                        st.success("✅ Password alterada.") if ok else st.error("Erro.")

    with tab_new_user:
        st.subheader("Criar Novo Utilizador")
        nu1, nu2 = st.columns(2)
        nu_name  = nu1.text_input("Nome completo *", key="nu_name")
        nu_email = nu2.text_input("Email *", key="nu_email")
        nu3, nu4 = st.columns(2)
        nu_role  = nu3.selectbox("Perfil *", ROLES,
                                 format_func=lambda r: ROLE_LABELS.get(r,r),
                                 key="nu_role")
        nu_pwd   = nu4.text_input("Password inicial *", type="password", key="nu_pwd")

        if st.button("➕ Criar Utilizador", type="primary", key="btn_nu"):
            if not nu_name or not nu_email or not nu_pwd:
                st.error("Preenche todos os campos obrigatórios.")
            else:
                ok, msg = add_user(nu_name, nu_email, nu_pwd, nu_role)
                if ok:
                    st.success(f"✅ Utilizador **{nu_name}** criado com perfil **{ROLE_LABELS.get(nu_role,nu_role)}**.")
                    st.rerun()
                else:
                    st.error(f"Erro: {msg}")
