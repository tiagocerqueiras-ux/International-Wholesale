"""
layouts.py — Layouts Admin/Stocks da proposta adjudicada (Fase 1, Passo 3)
===========================================================================
Dois layouts diferenciados por função:
- ADMINISTRATIVO (faturação): cliente + dados financeiros, e por linha
  SKU, Produto, QTD, Preço de Venda, Valor, Qtd/Palete, Paletes + totais (€).
- STOCKS (armazém): cliente + morada de entrega, e por linha
  SKU, EAN, Produto, QTD, PCL (do Simulador), Qtd/Palete, Paletes + totais.
"""
import html as _h


def _num(v):
    """Converte para float, tolerante a None/strings/'%'."""
    try:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.replace("€", "").replace(",", ".").replace("%", "").strip()
            if not v:
                return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _eur(v):
    n = _num(v)
    return f"{n:,.2f} €".replace(",", " ") if n is not None else "—"


def _fmt_addr(a: dict) -> str:
    if not a:
        return "—"
    parts = [a.get("address", ""), a.get("zip", ""), a.get("city", ""), a.get("country", "")]
    return ", ".join(p for p in parts if p) or "—"


_TH = "style='border:1px solid #ccc;padding:6px;background:#1B2744;color:#fff;text-align:left'"
_TD = "style='border:1px solid #ccc;padding:6px'"
_TDR = "style='border:1px solid #ccc;padding:6px;text-align:right'"


def _esc(v):
    return _h.escape(str(v)) if (v is not None and str(v).strip()) else "—"


# ── Blocos de cabeçalho ─────────────────────────────────────────────────────

def _admin_header(client, delivery, incoterm, payment):
    return (
        "<div style='margin:8px 0;line-height:1.6'>"
        f"<b>Cliente:</b> {_esc(client.get('company_name'))} "
        f"&nbsp;|&nbsp; <b>VAT:</b> {_esc(client.get('vat'))}<br>"
        f"<b>Email faturação:</b> {_esc(client.get('billing_email') or client.get('contact_email'))} "
        f"&nbsp;|&nbsp; <b>IBAN:</b> {_esc(client.get('iban'))}<br>"
        f"<b>Morada de entrega:</b> {_h.escape(_fmt_addr(delivery))}<br>"
        f"<b>Incoterm:</b> {_esc(incoterm)} "
        f"&nbsp;|&nbsp; <b>Pagamento:</b> {_esc(payment)}"
        "</div>"
    )


def _stocks_header(client, delivery, incoterm):
    return (
        "<div style='margin:8px 0;line-height:1.6'>"
        f"<b>Cliente:</b> {_esc(client.get('company_name'))}<br>"
        f"<b>Contacto:</b> {_esc(client.get('contact_name'))} · "
        f"{_esc(client.get('contact_email'))} · {_esc(client.get('contact_phone'))}<br>"
        f"<b>Morada de entrega:</b> {_h.escape(_fmt_addr(delivery))} "
        f"&nbsp;|&nbsp; <b>Incoterm:</b> {_esc(incoterm)}"
        "</div>"
    )


# ── Tabelas ─────────────────────────────────────────────────────────────────

def _admin_table(lines, include_pallets):
    head = (f"<th {_TH}>SKU</th><th {_TH}>Produto</th><th {_TH}>QTD</th>"
            f"<th {_TH}>Preço Venda (€)</th><th {_TH}>Valor (€)</th>")
    if include_pallets:
        head += f"<th {_TH}>Qtd/Palete</th><th {_TH}>Paletes</th>"
    body, subtotal = "", 0.0
    for ln in lines:
        qty = _num(ln.get("qty")) or 0
        price = _num(ln.get("price"))
        valor = (qty * price) if price is not None else None
        if valor is not None:
            subtotal += valor
        body += "<tr>"
        body += f"<td {_TD}>{_esc(ln.get('sku'))}</td>"
        body += f"<td {_TD}>{_esc(ln.get('name'))}</td>"
        body += f"<td {_TDR}>{int(qty)}</td>"
        body += f"<td {_TDR}>{_eur(price)}</td>"
        body += f"<td {_TDR}>{_eur(valor)}</td>"
        if include_pallets:
            body += f"<td {_TDR}>{ln.get('upp') or '—'}</td>"
            body += f"<td {_TDR}>{ln.get('pallets') if ln.get('pallets') is not None else '—'}</td>"
        body += "</tr>"
    table = f"<table style='border-collapse:collapse;width:100%'><tr>{head}</tr>{body}</table>"
    return table, subtotal


def _stocks_table(lines, include_pallets):
    head = (f"<th {_TH}>SKU</th><th {_TH}>EAN</th><th {_TH}>Produto</th>"
            f"<th {_TH}>QTD</th><th {_TH}>PCL (€)</th>")
    if include_pallets:
        head += f"<th {_TH}>Qtd/Palete</th><th {_TH}>Paletes</th>"
    body, total_qty = "", 0
    for ln in lines:
        qty = int(_num(ln.get("qty")) or 0)
        total_qty += qty
        body += "<tr>"
        body += f"<td {_TD}>{_esc(ln.get('sku'))}</td>"
        body += f"<td {_TD}>{_esc(ln.get('ean'))}</td>"
        body += f"<td {_TD}>{_esc(ln.get('name'))}</td>"
        body += f"<td {_TDR}>{qty}</td>"
        body += f"<td {_TDR}>{_eur(ln.get('pcl'))}</td>"
        if include_pallets:
            body += f"<td {_TDR}>{ln.get('upp') or '—'}</td>"
            body += f"<td {_TDR}>{ln.get('pallets') if ln.get('pallets') is not None else '—'}</td>"
        body += "</tr>"
    table = f"<table style='border-collapse:collapse;width:100%'><tr>{head}</tr>{body}</table>"
    return table, total_qty


# ── API ─────────────────────────────────────────────────────────────────────

def build_layouts(deal_id, client, delivery, lines, incoterm, transport,
                  include_pallets=True, total_pallets=0, payment=""):
    """Devolve (admin_html, stocks_html) diferenciados."""
    transport = _num(transport) or 0.0
    ref = f"<p style='color:#888;font-size:12px'>Ref. proposta: {_esc(deal_id)}</p>"

    # ── Administrativo ──
    a_table, subtotal = _admin_table(lines, include_pallets)
    total_fatura = subtotal + transport
    a_tot = (
        "<div style='margin:8px 0;text-align:right;line-height:1.7'>"
        f"<b>Subtotal:</b> {_eur(subtotal)} &nbsp;|&nbsp; "
        f"<b>Transporte:</b> {_eur(transport)} &nbsp;|&nbsp; "
        f"<b>Total fatura:</b> {_eur(total_fatura)}"
        + (f"<br><b>Total paletes:</b> {total_pallets}" if include_pallets else "")
        + "</div>"
    )
    admin = (f"<h2>📋 Layout Administrativo — {_esc(deal_id)}</h2>"
             + _admin_header(client, delivery, incoterm, payment)
             + a_table + a_tot + ref)

    # ── Stocks ──
    s_table, total_qty = _stocks_table(lines, include_pallets)
    s_tot = (
        "<div style='margin:8px 0;text-align:right;line-height:1.7'>"
        f"<b>Total unidades:</b> {total_qty}"
        + (f" &nbsp;|&nbsp; <b>Total paletes:</b> {total_pallets}" if include_pallets else "")
        + "</div>"
    )
    stocks = (f"<h2>📦 Layout Stocks — {_esc(deal_id)}</h2>"
              + _stocks_header(client, delivery, incoterm)
              + s_table + s_tot + ref)

    return admin, stocks
