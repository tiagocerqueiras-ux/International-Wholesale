"""
Email Generator — Geração de propostas e follow-ups com Claude API
==================================================================
Usa a API Anthropic para produzir emails HTML profissionais.

Funções principais:
  generate_proposal()  — email de cotação/proposta comercial
  generate_followup()  — email de follow-up de proposta pendente
"""

import base64
import anthropic
from pathlib import Path
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
    USER_NAME, USER_TITLE, USER_EMAIL, USER_PHONE, COMPANY_NAME,
    WAREHOUSE, INCOTERM, PAYMENT_CONDITIONS_DEFAULT,
)

# ── Logo Worten (base64 inline para funcionar em email/Outlook) ───────────────
_LOGO_PATH = Path(__file__).parent.parent / "Docs" / "Assinatura_vf.png"

def _logo_b64() -> str:
    """Devolve o logo como data URI base64, ou string vazia se o ficheiro não existir."""
    try:
        with open(_LOGO_PATH, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except Exception:
        return ""

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Texto obrigatório sobre VAT e transporte ──────────────────────────────────

VAT_TRANSPORT_NOTE = (
    "If you choose to arrange your own collection, a VAT deposit will be required. "
    "This deposit will be fully refunded upon receipt of the official export documentation.\n"
    "Alternatively, if Worten manages the delivery, a transport quotation will be provided. "
    "Freight costs will be invoiced separately and added to the prices indicated above."
)


# ── Formatação dos dados de produtos ─────────────────────────────────────────

def _build_products_context(skus_data: dict) -> tuple[str, str]:
    """
    Gera dois blocos para o prompt:
      1. product_rows  — linhas prontas para a tabela HTML (pipe-separated)
      2. support_notes — flags de sell-in/sell-out/eis para rodapé
    """
    rows  = []
    notes = []

    for sku, info in skus_data.items():
        d        = info.get("data") or {}
        qty      = int(info.get("qty") or 1)
        pvp      = info.get("pvp") or 0.0
        ean      = d.get("ean") or "N/A"
        name     = d.get("name", sku)[:70]
        brand    = d.get("brand") or "N/A"
        pvp_pt   = d.get("pvp_pt")
        eis_da   = d.get("eis_da") or 0.0
        sell_in  = d.get("sell_in")
        sell_out = d.get("sell_out")

        pvp_pt_str = f"{pvp_pt:.2f}" if pvp_pt is not None else "N/A"
        total      = round(pvp * qty, 2)

        rows.append(
            f"| {ean} | {sku} | {name} | {brand} | {pvp_pt_str} | {pvp:.2f} | {qty} | {total:.2f} |"
        )

        if eis_da > 0:
            notes.append(f"SKU {sku}: EIS Direitos Autor {eis_da:.2f} EUR/unit included in price")
        if sell_in:
            notes.append(f"SKU {sku}: Sell-In support {sell_in:.2f} EUR/unit available")
        if sell_out:
            notes.append(f"SKU {sku}: Sell-Out support {sell_out:.2f} EUR/unit available")

    return "\n".join(rows), "\n".join(notes) if notes else "none"


def _wrap_html(body: str) -> str:
    """Envolve o body em HTML completo para visualização no browser."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * {{ font-family: Aptos, Calibri, 'Segoe UI', Arial, sans-serif !important; box-sizing: border-box; }}
    body {{
      font-size: 14px;
      max-width: 780px;
      margin: 32px auto;
      padding: 0 24px 32px;
      color: #2c2c2c;
      line-height: 1.6;
      background: #ffffff;
    }}
    p {{ margin: 0 0 10px; }}
    h3 {{ color: #CC0000; font-size: 13px; text-transform: uppercase;
          letter-spacing: .5px; margin: 20px 0 6px; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 16px auto;
    }}
    th {{
      background: #CC0000;
      color: #ffffff;
      padding: 9px 12px;
      text-align: center;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: .3px;
    }}
    td {{
      border: 1px solid #f0c0c0;
      padding: 7px 12px;
      font-size: 13px;
      text-align: center;
      vertical-align: middle;
    }}
    td:nth-child(3) {{ text-align: left; }}
    tr:nth-child(even) td {{ background: #fdeaea; }}
    tr:hover td {{ background: #fad0d0; }}
    .total-row td {{
      background: #CC0000 !important;
      color: white;
      font-weight: bold;
      font-size: 13px;
    }}
    .summary-table {{
      width: 320px;
      margin: 12px 0 12px auto;
      border-collapse: collapse;
    }}
    .summary-table td {{
      border: none;
      padding: 4px 10px;
      font-size: 13px;
      text-align: right;
    }}
    .summary-table .lbl {{ color: #555; text-align: left; }}
    .summary-table .total-line td {{
      border-top: 2px solid #CC0000;
      font-weight: bold;
      color: #CC0000;
      font-size: 14px;
      padding-top: 6px;
    }}
    .note-box {{
      background: #fff5f5;
      border-left: 4px solid #CC0000;
      padding: 12px 16px;
      margin: 20px 0;
      font-size: 12.5px;
      color: #444;
      border-radius: 0 4px 4px 0;
    }}
    .conditions {{
      background: #f5f5f5;
      border: 1px solid #e0e0e0;
      border-left: 4px solid #CC0000;
      border-radius: 0 4px 4px 0;
      padding: 14px 16px;
      margin: 20px 0;
      font-size: 13px;
    }}
    .conditions table {{ width: 100%; border-collapse: collapse; margin: 0; }}
    .conditions td {{ border: none; padding: 6px 8px; font-size: 13px;
                      text-align: left; vertical-align: top; background: transparent; }}
    .conditions tr:nth-child(even) td {{ background: #ececec; }}
    .conditions .lbl {{ color: #333; font-weight: 600; width: 200px; }}
    .signature {{
      margin-top: 32px;
      padding-top: 20px;
      padding-left: 20px;
      border-top: 1px solid #e0e0e0;
      font-size: 13px;
      font-family: Aptos, Calibri, 'Segoe UI', Arial, sans-serif;
      color: #444;
      line-height: 1.8;
    }}
    .signature b {{ color: #222; font-size: 14px; font-family: Aptos, Calibri, 'Segoe UI', Arial, sans-serif; }}
    .signature img {{ display: block; margin-bottom: 12px; max-height: 60px; }}
    .footnote {{ font-size: 11px; color: #888; margin-top: 6px; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


# ── Geração de Proposta ───────────────────────────────────────────────────────

def generate_proposal(
    client_name: str,
    client_email: str,
    country: str,
    language: str,
    skus_data: dict,
    deal_id: str,
    margin: float = 0.05,
    margin_mode: str = "Percentagem (%)",
    margin_val: float = 5.0,
    notes: str = "",
    incoterm: str = None,
    payment_conditions: str = None,
    freight_cost: float = 0.0,
    vat_rate: float = 0.0,
    availability: str = "Ex-stock",
) -> tuple[str, float, float]:
    """
    Gera um email HTML de proposta comercial.

    Args:
        skus_data:           {sku: {"qty": int, "data": {...}, "pvp": float}}
        margin_mode:         "Percentagem (%)" ou "Valor (€/un.)"
        margin_val:          Valor da margem (% ou €/un. conforme mode)
        incoterm:            Incoterm selecionado (override da config)
        payment_conditions:  Condições de pagamento (override da config)

    Returns:
        (html_body, pvp_total, margin_pct)
    """
    lang_map  = {"EN": "English", "PT": "Português", "ES": "Español", "FR": "Français"}
    lang_full = lang_map.get(language.upper(), "English")

    effective_incoterm = incoterm or INCOTERM
    effective_payment  = payment_conditions or PAYMENT_CONDITIONS_DEFAULT

    # Calcular PVPs e totais — usa fc_final e pvp pré-calculados
    pvp_total  = 0.0
    cost_total = 0.0
    for sku, info in skus_data.items():
        d        = info.get("data") or {}
        qty      = int(info.get("qty") or 1)
        fc_final = info.get("fc_final") or d.get("ufc_raw") or 0.0

        pvp = info.get("pvp")
        if pvp is None:
            if margin_mode == "Valor (€/un.)":
                pvp = round(fc_final + margin_val, 4)
            else:
                pvp = round(fc_final * (1 + margin_val / 100), 4)
            info["pvp"] = pvp

        pvp_total  += pvp * qty
        cost_total += fc_final * qty

    margin_pct = ((pvp_total - cost_total) / pvp_total * 100) if pvp_total else 0.0
    product_rows, support_notes = _build_products_context(skus_data)
    n_skus = len(skus_data)

    # Logo para a assinatura
    _logo_src = _logo_b64()
    logo_img_html = (
        f'<img src="{_logo_src}" alt="Worten" '
        f'style="max-height:60px;display:block;margin-bottom:8px;">'
        if _logo_src else ""
    )

    # Pre-calculate financial totals
    freight    = freight_cost or 0.0
    subtotal   = round(pvp_total, 2)
    vat_amount = round((subtotal + freight) * vat_rate, 2)
    grand_total = round(subtotal + freight + vat_amount, 2)
    freight_str = "TBD (transport quotation to follow)" if not freight else f"{freight:.2f} EUR"
    vat_str     = f"Exempt — Export sale (0%)" if vat_rate == 0 else f"IVA 23% — {vat_amount:.2f} EUR"

    prompt = f"""You are {USER_NAME} from {COMPANY_NAME}.
Write a complete, professional B2B commercial proposal email in {lang_full}.

RECIPIENT:
  Name: {client_name}
  Email: {client_email}
  Country: {country}
  Deal Reference: {deal_id}

PRODUCTS TABLE DATA ({n_skus} products — include ALL rows, one per line):
Columns: EAN | SKU | Product | Brand | PVP PT (ref.) | Unit Price (EUR) | Qty | Total (EUR)
{product_rows}

Note: "PVP PT (ref.)" is Portuguese retail price (market reference only). "Unit Price" is the agreed sale price. "Total (EUR)" = Unit Price × Qty (already calculated above).

SUPPORT / EIS NOTES (use as footnotes below table if not "none"):
{support_notes}

COMMERCIAL CONDITIONS (MANDATORY — must appear in the email):
  Incoterm: {effective_incoterm}
  Warehouse: {WAREHOUSE}
  Payment Conditions: {effective_payment}
  Availability / ETA: {availability or "Ex-stock"}

FINANCIAL SUMMARY (show exactly these values):
  Products subtotal : {subtotal:.2f} EUR
  Freight / Transport: {freight_str}
  VAT               : {vat_str}
  TOTAL             : {grand_total:.2f} EUR

EXTRA NOTES / SPECIAL INSTRUCTIONS: {notes or "none"}

INSTRUCTIONS:
1. Write the full email body in {lang_full}
2. Start with the branded header (below), then <p>Dear {client_name},</p> (or equivalent in {lang_full}), then opening paragraph:
   "Please find below our commercial proposal for your review, issued under deal reference {deal_id}. All prices are quoted in EUR and represent our best commercial conditions for the indicated quantities."
3. Render the products table with ALL {n_skus} rows — do NOT skip, merge, or omit any product. Use the exact data from PRODUCTS TABLE DATA above.
4. After the table add the SUPPORT/EIS footnotes (if any).
5. Show the financial summary as a right-aligned summary block using class="summary-table". Bold the TOTAL line.
6. After the financial summary include the VAT/transport note box (class="note-box"):
   "{VAT_TRANSPORT_NOTE}"
7. Include a COMMERCIAL CONDITIONS section using this EXACT HTML structure (no changes):
   <div class="conditions">
     <h3>Commercial Conditions</h3>
     <table><tbody>
       <tr><td class="lbl">Incoterm</td><td>{effective_incoterm}</td></tr>
       <tr><td class="lbl">Payment Conditions</td><td>{effective_payment}</td></tr>
       <tr><td class="lbl">Availability / ETA</td><td>{availability or "Ex-stock"}</td></tr>
     </tbody></table>
   </div>
8. End your output immediately after closing the conditions div — do NOT add any closing salutation, signature, or extra content after it.
9. Do NOT mention stock levels or warehouse quantities anywhere.
10. Be professional, concise, B2B focused.

CRITICAL FORMATTING RULES — DO NOT DEVIATE UNDER ANY CIRCUMSTANCES:
- Return ONLY raw HTML — NO markdown fences (no ```html, no ```, no backticks)
- font-family: Aptos, Calibri, 'Segoe UI', Arial, sans-serif — NO other fonts ever
- All table columns centered except Product column (left-aligned)
- Use ONLY these CSS classes: note-box, summary-table, conditions, footnote, total-row
- NEVER add inline style attributes that set colour, font-family, or background-color
- Primary colour: #CC0000 (Worten red) ONLY — absolutely no blues, greens or other colours
- Table alternate rows: #fdeaea — do not change
- Section backgrounds: white only — no coloured backgrounds on divs or sections
- NEVER invent new styles — the CSS is already defined in the wrapper

Start with this EXACT branded header HTML:
<div style="background:#CC0000;padding:20px 28px;border-radius:6px 6px 0 0;margin-bottom:24px;position:relative;">
  <span style="color:white;font-size:26px;font-weight:900;letter-spacing:-1px;font-family:Aptos,Calibri,'Segoe UI',Arial,sans-serif;">worten</span>
  <span style="color:#ffaaaa;font-size:13px;margin-left:16px;font-family:Aptos,Calibri,'Segoe UI',Arial,sans-serif;">International Wholesale</span>
  <span style="color:#ffcccc;font-size:12px;float:right;margin-top:8px;font-family:Aptos,Calibri,'Segoe UI',Arial,sans-serif;">Ref: {deal_id}</span>
</div>
"""

    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    html_body = response.content[0].text.strip()

    # 1. Remover markdown fences se Claude as incluir
    if html_body.startswith("```"):
        html_body = html_body.split("\n", 1)[-1]
    if html_body.endswith("```"):
        html_body = html_body.rsplit("```", 1)[0]
    html_body = html_body.strip()

    # 2. Se Claude devolveu documento HTML completo, extrair só o <body>
    if html_body.lower().startswith("<!doctype") or "<html" in html_body[:100].lower():
        import re
        body_match = re.search(r"<body[^>]*>(.*?)</body>", html_body, re.DOTALL | re.IGNORECASE)
        if body_match:
            html_body = body_match.group(1).strip()

    # 3. Remover font-family dos inline styles do Claude (o CSS wrapper já define o font)
    import re as _re2
    html_body = _re2.sub(
        r'font-family\s*:[^;"\'}]+[;]?',
        '',
        html_body, flags=_re2.IGNORECASE
    )
    # Remover font face tags antigas
    html_body = _re2.sub(r'<font\s[^>]*>', '', html_body, flags=_re2.IGNORECASE)
    html_body = _re2.sub(r'</font>', '', html_body, flags=_re2.IGNORECASE)

    # 4. Acrescentar assinatura programaticamente no lugar certo
    logo_src = _logo_b64()
    logo_tag = (
        f'<img src="{logo_src}" alt="Worten" '
        f'style="max-height:55px;display:block;margin-bottom:10px;">'
        if logo_src else ""
    )
    signature_html = f"""
<div class="signature" style="font-family:Aptos,Calibri,'Segoe UI',Arial,sans-serif;margin-top:32px;margin-left:0;padding-left:0;padding-top:20px;border-top:1px solid #e0e0e0;font-size:13px;color:#444;line-height:1.8;">
  {logo_tag}
  <b style="color:#222;font-size:14px;font-family:Aptos,Calibri,'Segoe UI',Arial,sans-serif;">{USER_NAME}</b><br>
  <span style="color:#555;font-family:Aptos,Calibri,'Segoe UI',Arial,sans-serif;">{COMPANY_NAME}</span><br>
  <span style="white-space:nowrap;font-family:Aptos,Calibri,'Segoe UI',Arial,sans-serif;">
    <a href="mailto:{USER_EMAIL}" style="color:#CC0000;text-decoration:none;font-family:Aptos,Calibri,'Segoe UI',Arial,sans-serif;">{USER_EMAIL}</a>
    &nbsp;·&nbsp; {USER_PHONE}
  </span>
</div>"""
    # Garantir que a assinatura fica SEMPRE no final, fora de qualquer div
    # Remover qualquer "Kind regards" gerado pelo Claude para evitar duplicado
    import re as _re
    html_body = _re.sub(
        r'<p[^>]*>\s*(kind regards|best regards|com os melhores cumprimentos'
        r'|cordialement|atentamente)[^<]*</p>',
        '', html_body, flags=_re.IGNORECASE
    )
    closing_lang = {
        "EN": "Kind regards,", "PT": "Com os melhores cumprimentos,",
        "ES": "Atentamente,", "FR": "Cordialement,",
    }
    closing = closing_lang.get(language.upper(), "Kind regards,")
    html_body = (
        html_body.rstrip()
        + f'\n<p style="margin-top:24px;margin-left:0;padding-left:0;font-family:Aptos,Calibri,\'Segoe UI\',Arial,sans-serif;font-size:14px;color:#333;">{closing}</p>'
        + signature_html
    )

    return html_body, round(pvp_total, 2), round(margin_pct, 2)


# ── Geração de Follow-up ──────────────────────────────────────────────────────

def generate_followup(
    deal: dict,
    language: str,
    days_since: int = 7,
    notes: str = "",
) -> str:
    """
    Gera um email HTML de follow-up para uma proposta pendente.

    Returns:
        html_body — conteúdo HTML do email
    """
    lang_map  = {"EN": "English", "PT": "Português", "ES": "Español", "FR": "Français"}
    lang_full = lang_map.get(language.upper(), "English")

    prompt = f"""You are {USER_NAME} from {COMPANY_NAME}.
Write a concise, professional follow-up email in {lang_full}.

CONTEXT:
  Deal Reference: {deal.get('Deal ID')}
  Client: {deal.get('Cliente')} ({deal.get('País')})
  Products: {str(deal.get('Produtos', ''))[:200]}
  Proposed Value: {deal.get('Valor Proposto (€)', 'N/A')} EUR
  Proposal sent {days_since} day(s) ago
  Current Status: {deal.get('Status')}
  Notes: {notes or deal.get('Notas', '') or 'none'}

INSTRUCTIONS:
1. Write in {lang_full}
2. Keep it SHORT (3-5 sentences max) — just checking in
3. Reference the deal ID and original proposal
4. Be friendly but professional, not pushy
5. Offer to clarify any questions or adjust the proposal
6. Include a professional HTML signature for {USER_NAME} | {USER_TITLE} | {COMPANY_NAME} | {USER_EMAIL} | {USER_PHONE}

Return ONLY the HTML email body (no html/head/body tags).
"""

    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ── Guardar email em ficheiro HTML ────────────────────────────────────────────

def save_email_html(deal_id: str, html_body: str, email_type: str = "proposal") -> str:
    """
    Guarda o email como ficheiro HTML e abre no browser para revisão.

    Returns:
        Caminho do ficheiro gerado
    """
    import os
    from datetime import datetime
    from config import EMAILS_OUT_DIR

    EMAILS_OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp    = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{deal_id}_{email_type}_{stamp}.html"
    filepath = EMAILS_OUT_DIR / filename

    with open(str(filepath), "w", encoding="utf-8") as f:
        f.write(_wrap_html(html_body))

    print(f"  Email guardado: {filepath}")

    # Abrir no browser predefinido
    try:
        os.startfile(str(filepath))
    except Exception:
        pass

    return str(filepath)


# ── Emails internos de fecho de deal ─────────────────────────────────────────

def generate_closing_emails(deal: dict, departure_date: str, supplier_date: str = "") -> tuple[str, str]:
    """
    Gera dois emails internos quando um deal é fechado:
      - stocks_html  : para a equipa de stocks/logística
      - admin_html   : para a equipa administrativa
    Retorna (stocks_html, admin_html) como strings HTML completas.
    """
    from datetime import datetime

    deal_id   = deal.get("Deal ID", "")
    client    = deal.get("Cliente", "")
    country   = deal.get("País", "")
    incoterm  = deal.get("Incoterm", "—")
    skus_raw  = deal.get("_skus_detail") or {}
    now_str   = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── CSS base ──────────────────────────────────────────────────────────────
    base_css = """
    <style>
      * { font-family: Aptos, Calibri, 'Segoe UI', Arial, sans-serif !important; }
      body { max-width: 780px; margin: 24px auto; padding: 0 20px 32px; color: #2c2c2c; font-size: 14px; line-height: 1.6; }
      h2 { color: #CC0000; border-bottom: 2px solid #CC0000; padding-bottom: 6px; font-size: 16px; margin-bottom: 16px; }
      table { border-collapse: collapse; width: 100%; margin: 16px 0; }
      th { background: #CC0000; color: #fff; padding: 8px 12px; text-align: center; font-size: 12px; font-weight: 600; }
      td { border: 1px solid #f0c0c0; padding: 7px 10px; font-size: 13px; text-align: center; vertical-align: middle; }
      td.lft { text-align: left; }
      tr:nth-child(even) td { background: #fdeaea; }
      .meta { background: #f5f5f5; border-left: 4px solid #CC0000; padding: 10px 14px; margin: 12px 0; font-size: 13px; border-radius: 0 4px 4px 0; }
      .meta b { color: #CC0000; }
      .footer { font-size: 11px; color: #888; margin-top: 20px; border-top: 1px solid #eee; padding-top: 8px; }
    </style>"""

    header = f"""<div style="background:#CC0000;padding:14px 20px;margin-bottom:20px;">
      <span style="color:#fff;font-size:18px;font-weight:700;letter-spacing:1px;">WORTEN</span>
      <span style="color:#ffcccc;font-size:13px;margin-left:10px;">International Wholesale</span>
    </div>
    <div class="meta">
      <b>Deal ID:</b> {deal_id} &nbsp;|&nbsp;
      <b>Cliente:</b> {client} ({country}) &nbsp;|&nbsp;
      <b>Data de fecho:</b> {now_str}
    </div>"""

    # ── Linhas da tabela ──────────────────────────────────────────────────────
    stocks_rows = ""
    admin_rows  = ""

    for sku, info in skus_raw.items():
        d        = info.get("data") or {}
        qty      = int(info.get("qty") or 1)
        ean      = d.get("ean") or "N/A"
        name     = d.get("name", sku)[:60]
        pcl      = d.get("pcl") or d.get("ufc_raw") or 0.0
        sell_prc = info.get("fc_final") or info.get("pvp") or 0.0

        stocks_rows += f"""<tr>
          <td>{sku}</td><td>{ean}</td>
          <td>{pcl:.2f}</td>
          <td class="lft">{name}</td>
          <td>{qty}</td>
          <td>{client}</td>
          <td>{departure_date}</td>
          <td>{supplier_date or "—"}</td>
        </tr>"""

        admin_rows += f"""<tr>
          <td>{sku}</td><td>{ean}</td>
          <td>{sell_prc:.2f}</td>
          <td class="lft">{name}</td>
          <td>{qty}</td>
          <td>{client}</td>
          <td>{incoterm}</td>
        </tr>"""

    # ── Email Stocks ──────────────────────────────────────────────────────────
    stocks_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">{base_css}</head><body>
    {header}
    <h2>📦 Alerta Stocks — Deal Fechado</h2>
    <p>O seguinte deal foi fechado e necessita de processamento logístico:</p>
    <table>
      <tr>
        <th>SKU</th><th>EAN</th><th>PCL (€)</th>
        <th>Descrição</th><th>Qty</th><th>Cliente</th><th>Data Saída Cliente</th><th>Entrega Worten (Fornecedor)</th>
      </tr>
      {stocks_rows}
    </table>
    <div class="footer">Email gerado automaticamente por International Wholesale | Worten — {now_str}</div>
    </body></html>"""

    # ── Email Admin ───────────────────────────────────────────────────────────
    admin_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">{base_css}</head><body>
    {header}
    <h2>📋 Alerta Administrativo — Deal Fechado</h2>
    <p>O seguinte deal foi fechado e necessita de processamento administrativo:</p>
    <table>
      <tr>
        <th>SKU</th><th>EAN</th><th>Preço Venda (€)</th>
        <th>Descrição</th><th>Qty</th><th>Cliente</th><th>Incoterm Acordado</th>
      </tr>
      {admin_rows}
    </table>
    <div class="footer">Email gerado automaticamente por International Wholesale | Worten — {now_str}</div>
    </body></html>"""

    return stocks_html, admin_html
