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
)
from sku_lookup import lookup_skus, search_by_name, build_cache
from deal_tracker import add_deal, update_status, update_margin, list_deals, get_deal, deal_products_table
from email_generator import generate_proposal, generate_followup, save_email_html, generate_closing_emails, generate_supplier_request
from email_sender import create_draft, build_subject
from client_tracker import (
    add_client, update_client, get_client, get_client_by_email,
    list_clients, count_clients, get_client_deals, bulk_import_clients,
    CLIENT_STATUSES, CLIENT_TYPES, MARKETS, BRANDS_LIST, CATEGORIES_LIST,
)
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

STATUS_EMOJI = {"Rascunho":"🟡","Enviado":"📤","Em Negociação":"🔄",
                "Follow-up":"🔁","Fechado":"✅","Perdido":"❌"}

# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="A carregar índice de SKUs...", ttl=3600)
def load_index():
    return build_cache()

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
              "margin_override","selected_incoterm","payment_conditions","vat_sel"]:
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

    st.markdown("Revê o email antes de enviar.")
    st.divider()
    st.components.v1.html(html_body, height=520, scrolling=True)
    st.divider()

    subject = build_subject(did, client, language)
    st.caption(f"**Para:** {to_email}  ·  **Assunto:** {subject}")

    c1, c2, c3 = st.columns([3, 2, 2])

    with c1:
        if st.button("🚀  Enviar Email", type="primary", use_container_width=True):
            ok, err = create_draft(to=to_email, subject=subject, html_body=html_body, send=True)
            if ok:
                save_email_html(did, html_body, "proposal")
                update_margin(did, pending["margin_calc"], pending["pvp_total"])
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
    c1, c2, c3, c4 = st.columns([2,1.5,2,1])
    client   = c1.text_input("Nome do cliente *", value=_crm_pre.get("client",""), placeholder="Ex: Geppit Group EOOD")
    country  = c2.text_input("País *", value=_crm_pre.get("country",""), placeholder="Ex: Bulgaria")
    email    = c3.text_input("Email do cliente *", value=_crm_pre.get("email",""), placeholder="Ex: contact@geppit.eu")
    language = c4.selectbox("Língua", ["EN","PT","ES","FR"])
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
        freight_cost = st.number_input("🚚 Frete (€)", min_value=0.0, value=0.0,
                                       step=50.0, format="%.2f",
                                       help="Custo de transporte a adicionar ao total da proposta")

    availability = st.text_input(
        "📦 Availability / ETA to Worten",
        placeholder="Ex: Ex-stock | Lead time 3–5 days | ETA 15 Apr 2026",
        help="Disponibilidade ou prazo de entrega a incluir na proposta"
    )
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

    btn_add, btn_clear = st.columns([2,6])
    add_clicked = btn_add.button("➕  Adicionar ao Cesto", type="primary")

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

    # ── Cesto de produtos ─────────────────────────────────────────────────────
    basket = st.session_state.get("product_basket", {})

    if basket:
        st.markdown("---")
        s_margin_mode = st.session_state.get("margin_mode", "Percentagem (%)")
        s_margin_val  = st.session_state.get("margin_val", 5.0)

        # Cabeçalho
        _unit = "%" if s_margin_mode == "Percentagem (%)" else "€"
        hcols = st.columns([0.5, 1.2, 1.5, 2.8, 1.4, 1.4, 1.4, 1.2, 1.6, 1.4, 1.4, 0.5])
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

            cols = st.columns([0.5, 1.2, 1.5, 2.8, 1.4, 1.4, 1.4, 1.2, 1.6, 1.4, 1.4, 0.5])

            if f"qty_{sku}" not in st.session_state:
                st.session_state[f"qty_{sku}"] = 1
            qty_map[sku] = cols[0].number_input("", min_value=1, step=1,
                                                key=f"qty_{sku}", label_visibility="collapsed")

            cols[1].markdown(f"**`{sku}`**")
            cols[2].markdown(f"`{ean}`")
            cols[3].markdown(f"{d.get('brand','')[:12]} · {d.get('name','')[:35]}")

            # FC_sim depende do destino (vat_rate vem da secção 2)
            if ufc_raw is not None:
                if vat_rate > 0:   # Portugal
                    fc_sim = round(ufc_raw + sell_out, 4)
                else:              # Exportação
                    fc_sim = round(ufc_raw - eis_total + sell_out, 4)
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

            cols[6].markdown(f"**{fmt4(fc_final)}**" if fc_final else "—")
            cols[8].markdown(f"**{fmt4(pvp)}**" if pvp else "—")
            cols[9].markdown(f"{'⚠️ ' if eis_da>0 else ''}{fmt4(eis_da) if eis_da>0 else '—'}")
            cols[10].markdown(f"{'✅ ' if sell_in else ''}{fmt4(sell_in) if sell_in else '—'}")

            if cols[11].button("✕", key=f"rm_{sku}", help="Remover produto"):
                del st.session_state["product_basket"][sku]
                st.session_state["so_manual"].pop(sku, None)
                st.session_state["margin_override"].pop(sku, None)
                st.rerun()

        if any_nd:
            st.markdown('<div class="warn-box">⚠️ Alguns SKUs sem FC disponível. '
                        'Verifica o simulador.</div>', unsafe_allow_html=True)

        # ── 4. Resumo financeiro ──────────────────────────────────────────────
        st.markdown("---")
        so_manual_map = st.session_state.get("so_manual", {})

        def _fc_sim_for(d):
            raw = d.get("ufc_raw") or 0
            eis = d.get("eis_total") or 0
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
        mc6.metric("Margem %", f"{overall_margin:.1f}%")

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
                                   salesperson_email=_cu.get("email",""))

            if criar_deal:
                st.success(f"✅ Deal **{deal_id}** criado como Rascunho.")
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
                        )
                        st.session_state["pending_email"] = {
                            "html_body":    html_body,
                            "deal_id":      deal_id,
                            "pvp_total":    pvp_calc,
                            "margin_calc":  margin_calc,
                            "client_email": email,
                            "client_name":  client,
                            "language":     language,
                        }
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao gerar email: {e}")
                        import traceback; st.code(traceback.format_exc())

        elif (criar_deal or criar_email) and not (client and email):
            st.error("⚠️ Preenche o **Nome do cliente** e **Email** antes de continuar.")


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA 2 — DEALS EM CURSO (inclui follow-up)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋  Deals em Curso":
    import pandas as pd
    st.title("📋 Deals em Curso")
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
                                html_body, pvp_calc, margin_calc = generate_proposal(
                                    client_name=str(deal.get("Cliente", "")),
                                    client_email=resend_to,
                                    country=str(deal.get("País", "")),
                                    language=str(deal.get("Língua", "EN")),
                                    skus_data=_skus,
                                    deal_id=did,
                                    notes=str(deal.get("Notas", "")),
                                    incoterm=str(deal.get("Incoterm", "")),
                                    payment_conditions=str(deal.get("Pagamento", "")),
                                    freight_cost=_freight,
                                    vat_rate=_vat_rate,
                                    availability=str(deal.get("Availability / ETA", "Ex-stock")),
                                )
                                st.session_state["pending_email"] = {
                                    "html_body":   html_body,
                                    "deal_id":     did,
                                    "pvp_total":   pvp_calc,
                                    "margin_calc": margin_calc,
                                    "client_email": resend_to,
                                    "client_name": str(deal.get("Cliente", "")),
                                    "language":    str(deal.get("Língua", "EN")),
                                }
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao gerar proposta: {e}")
                                import traceback; st.code(traceback.format_exc())

                # ── Follow-up (só se deal enviado/em negociação) ───────────
                if status in ("Enviado", "Em Negociação", "Follow-up", "Rascunho"):
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
                                fu_sub = build_subject(did, cl, str(deal.get("Língua","EN")))
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

    # ── Tabela de produtos ────────────────────────────────────────────────────
    sup_basket = st.session_state["sup_basket"]
    if sup_basket:
        st.markdown("---")
        # Cabeçalho
        sh = st.columns([0.5, 1.2, 1.5, 3.5, 1.6, 1.6, 1.6, 0.5])
        for col, lbl in zip(sh, ["Qty","SKU","EAN","Produto","FC Simulador","SO Negoc. (€)","FC Final","✕"]):
            col.caption(lbl)
        st.markdown("---")

        sup_qty_map = {}
        for sku, d in list(sup_basket.items()):
            ufc_raw   = d.get("ufc_raw")
            eis_total = d.get("eis_total") or 0.0
            sell_out  = d.get("sell_out") or 0.0
            ean       = d.get("ean") or "—"
            name      = f"{d.get('brand','')} · {d.get('name','')[:40]}"

            sc = st.columns([0.5, 1.2, 1.5, 3.5, 1.6, 1.6, 1.6, 0.5])
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
                                         help="Apoio Sell-Out a negociar com o fornecedor (€/un.)")
            st.session_state["sup_so_manual"][sku] = so_neg

            fc_final = round(fc_sim - so_neg, 4) if fc_sim is not None else None
            sc[6].markdown(f"**{fmt4(fc_final)}**" if fc_final is not None else "—")

            if sc[7].button("✕", key=f"srm_{sku}"):
                del st.session_state["sup_basket"][sku]
                st.session_state["sup_so_manual"].pop(sku, None)
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
    tab_list, tab_new, tab_import = st.tabs(["📋 Lista de Clientes", "➕ Novo Cliente", "📥 Importar"])

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
                cid    = str(c.get("id",""))
                cname  = c.get("company_name","—")
                cctry  = c.get("country","—")
                cstat  = c.get("status","—")
                cemail = c.get("contact_email","")
                ctype  = c.get("client_type","—")
                cphone = c.get("contact_phone","")
                brands = c.get("brands") or []

                with st.expander(
                    f"{STATUS_ICON.get(cstat,'⚪')} **{cname}** — {cctry}  ·  {ctype}  ·  {cstat}"
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

                            e9, e10, e11 = st.columns(3)
                            e_cname  = e9.text_input("Contacto — Nome", value=full.get("contact_name",""), key=f"ecn_{cid}")
                            e_cemail = e10.text_input("Contacto — Email", value=full.get("contact_email",""), key=f"ece_{cid}")
                            e_cphone = e11.text_input("Contacto — Telefone", value=full.get("contact_phone",""), key=f"ecp_{cid}")

                            e12, e13 = st.columns(2)
                            e_inc    = e12.text_input("Incoterm", value=full.get("incoterm",""), key=f"einc_{cid}")
                            e_pay    = e13.text_input("Condições Pagamento", value=full.get("payment_terms",""), key=f"epay_{cid}")

                            e_brands = st.multiselect("Marcas", BRANDS_LIST,
                                default=[b for b in (full.get("brands") or []) if b in BRANDS_LIST],
                                key=f"ebr_{cid}")
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
                                    "contact_name":  e_cname,
                                    "contact_email": e_cemail,
                                    "contact_phone": e_cphone,
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
                    # Normalizar: arrays de texto para brands/categories se existirem
                    for r in rows:
                        for arr_col in ("brands", "categories"):
                            if arr_col in r and isinstance(r[arr_col], str):
                                r[arr_col] = [x.strip() for x in r[arr_col].split(",") if x.strip()]
                            elif arr_col not in r:
                                r[arr_col] = []
                    with st.spinner(f"A importar {len(rows)} clientes..."):
                        ok_n, err_n = bulk_import_clients(rows)
                    st.success(f"✅ {ok_n} clientes importados.")
                    if err_n:
                        st.warning(f"⚠️ {err_n} erros.")
                    st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler ficheiro: {e}")

        st.markdown("---")
        st.caption(f"Total de clientes na base de dados: **{count_clients()}**")


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
