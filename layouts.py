"""
layouts.py — Layouts Admin/Stocks da proposta adjudicada (Fase 1, Passo 3)
===========================================================================
Gera HTML com os campos exigidos: DADOS DO CLIENTE, MORADA DE ENTREGA, SKU,
EAN, QTD, PREÇO DE VENDA, INCOTERM, PREÇO DO TRANSPORTE, QUANTIDADE POR PALETE.
"""
import html as _h


def _fmt_addr(a: dict) -> str:
    if not a:
        return "—"
    parts = [a.get("address", ""), a.get("zip", ""), a.get("city", ""), a.get("country", "")]
    return ", ".join(p for p in parts if p) or "—"


def _client_block(client: dict, delivery: dict) -> str:
    return (
        "<div style='margin:8px 0'>"
        f"<b>Cliente:</b> {_h.escape(str(client.get('company_name') or '—'))} "
        f"&nbsp;|&nbsp; <b>VAT:</b> {_h.escape(str(client.get('vat') or '—'))}<br>"
        f"<b>Contacto:</b> {_h.escape(str(client.get('contact_name') or '—'))} · "
        f"{_h.escape(str(client.get('contact_email') or '—'))} · "
        f"{_h.escape(str(client.get('contact_phone') or '—'))}<br>"
        f"<b>Morada de entrega:</b> {_h.escape(_fmt_addr(delivery))}"
        "</div>"
    )


def _lines_table(lines: list, include_pallets: bool) -> str:
    th = "style='border:1px solid #ccc;padding:6px;background:#1B2744;color:#fff;text-align:left'"
    td = "style='border:1px solid #ccc;padding:6px'"
    head = f"<th {th}>SKU</th><th {th}>EAN</th><th {th}>Produto</th><th {th}>QTD</th><th {th}>Preço Venda (€)</th>"
    if include_pallets:
        head += f"<th {th}>Qtd/Palete</th><th {th}>Paletes</th>"
    body = ""
    for ln in lines:
        body += "<tr>"
        body += f"<td {td}>{_h.escape(str(ln.get('sku','')))}</td>"
        body += f"<td {td}>{_h.escape(str(ln.get('ean','') or '—'))}</td>"
        body += f"<td {td}>{_h.escape(str(ln.get('name','') or ''))}</td>"
        body += f"<td {td}>{ln.get('qty','')}</td>"
        body += f"<td {td}>{ln.get('price','')}</td>"
        if include_pallets:
            body += f"<td {td}>{ln.get('upp') or '—'}</td>"
            body += f"<td {td}>{ln.get('pallets') if ln.get('pallets') is not None else '—'}</td>"
        body += "</tr>"
    return f"<table style='border-collapse:collapse;width:100%'><tr>{head}</tr>{body}</table>"


def _common(deal_id, client, delivery, lines, incoterm, transport, include_pallets, total_pallets):
    return (
        _client_block(client, delivery)
        + f"<div style='margin:8px 0'><b>Incoterm:</b> {_h.escape(str(incoterm or '—'))} "
          f"&nbsp;|&nbsp; <b>Preço do transporte:</b> {transport:,.2f} €"
        + (f" &nbsp;|&nbsp; <b>Total paletes:</b> {total_pallets}" if include_pallets else "")
        + "</div>"
        + _lines_table(lines, include_pallets)
        + f"<p style='color:#888;font-size:12px'>Ref. proposta: {_h.escape(str(deal_id))}</p>"
    )


def build_layouts(deal_id, client, delivery, lines, incoterm, transport,
                  include_pallets=True, total_pallets=0):
    """Devolve (admin_html, stocks_html)."""
    body = _common(deal_id, client, delivery, lines, incoterm, transport, include_pallets, total_pallets)
    admin = f"<h2>📋 Layout Administrativo — {_h.escape(str(deal_id))}</h2>{body}"
    # Stocks: paletes opcionais (mostra se incluído)
    stocks = f"<h2>📦 Layout Stocks — {_h.escape(str(deal_id))}</h2>{body}"
    return admin, stocks
