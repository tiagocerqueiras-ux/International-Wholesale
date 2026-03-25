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
from email_generator import generate_proposal, generate_followup, save_email_html, generate_closing_emails
from email_sender import create_draft, build_subject

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
              "selected_incoterm","payment_conditions","vat_sel"]:
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

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📦 International Wholesale")
    st.markdown("**Cotação Agent**")
    st.markdown("---")
    page = st.radio("Nav", ["🆕  Nova Cotação","📋  Deals em Curso",
                             "🔍  Pesquisar Produto"],
                    label_visibility="collapsed")
    st.markdown("---")
    st.markdown("*Tiago Cerqueira*")
    st.markdown("*tdcerqueira@worten.pt*")

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

    # ── 1. Cliente ────────────────────────────────────────────────────────────
    st.subheader("1. Dados do Cliente")
    c1, c2, c3, c4 = st.columns([2,1.5,2,1])
    client   = c1.text_input("Nome do cliente *", placeholder="Ex: Geppit Group EOOD")
    country  = c2.text_input("País *", placeholder="Ex: Bulgaria")
    email    = c3.text_input("Email do cliente *", placeholder="Ex: contact@geppit.eu")
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
        hcols = st.columns([0.5, 1.2, 1.5, 2.8, 1.4, 1.4, 1.6, 1.6, 1.6, 1.4, 0.5])
        for col, lbl in zip(hcols, ["Qty","SKU","EAN","Produto",
                                     "FC Simulador","SO Negoc. (€)","FC Final",
                                     "Preço Cliente","EIS DA","Sell-In","✕"]):
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

            cols = st.columns([0.5, 1.2, 1.5, 2.8, 1.4, 1.4, 1.6, 1.6, 1.6, 1.4, 0.5])

            qty_map[sku] = cols[0].number_input("", min_value=1, value=1, step=1,
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
            pvp = calc_pvp(fc_final, s_margin_mode, s_margin_val)

            cols[6].markdown(f"**{fmt4(fc_final)}**" if fc_final else "—")
            cols[7].markdown(f"**{fmt4(pvp)}**" if pvp else "—")
            cols[8].markdown(f"{'⚠️ ' if eis_da>0 else ''}{fmt4(eis_da) if eis_da>0 else '—'}")
            cols[9].markdown(f"{'✅ ' if sell_in else ''}{fmt4(sell_in) if sell_in else '—'}")

            if cols[10].button("✕", key=f"rm_{sku}", help="Remover produto"):
                del st.session_state["product_basket"][sku]
                st.session_state["so_manual"].pop(sku, None)
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

        total_fc_final = sum(
            round(_fc_sim_for(basket[s]) - so_manual_map.get(s, 0), 4) * qty_map[s]
            for s in basket
        )
        total_pvp = sum(
            (calc_pvp(round(_fc_sim_for(basket[s]) - so_manual_map.get(s, 0), 4),
                      s_margin_mode, s_margin_val) or 0) * qty_map[s]
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
                so_neg   = so_manual_map.get(sku, 0.0)
                fc_sim   = _fc_sim_for(basket[sku])
                fc_final = round(fc_sim - so_neg, 4)
                pvp_unit = calc_pvp(fc_final, s_margin_mode, s_margin_val)
                skus_data[sku] = {
                    "qty":     qty_map[sku],
                    "data":    basket[sku],
                    "so_neg":  so_neg,
                    "fc_final": fc_final,
                    "pvp":     pvp_unit,
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
                                   availability=availability)

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

    deals = list_deals(None if status_filter=="Todos" else status_filter)
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
                dep_date = fd1.text_input("Data prevista de saída", placeholder="ex: 15/04/2026",
                                          key=f"dep_{did}")
                stocks_to = fd2.text_input("Email Stocks",
                                           value=STOCKS_EMAIL,
                                           key=f"sto_{did}",
                                           help="Separa vários emails com ;")
                fd3, fd4 = st.columns(2)
                admin_to = fd3.text_input("Email Administrativo",
                                          value=ADMIN_EMAIL,
                                          key=f"adm_{did}",
                                          help="Separa vários emails com ;")
                if fd4.button("✅ Fechar & Enviar Alertas Internos",
                              key=f"close_{did}", type="primary",
                              use_container_width=True):
                    if not dep_date:
                        st.warning("Indica a data prevista de saída.")
                    elif not (stocks_to or admin_to):
                        st.warning("Indica pelo menos um email de destino.")
                    else:
                        with st.spinner("A gerar e enviar alertas internos..."):
                            try:
                                stocks_html, admin_html = generate_closing_emails(deal, dep_date)
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
