"""
Daily Business Briefing — BoxMovers / TDC
==========================================
Executa diariamente (via Windows Task Scheduler).

O que faz:
  1. Lê deals activos (PO) do BoxMovers Excel
  2. Lê pipeline do Supabase (cotacao_agent)
  3. Analisa tendências de procura por categoria/marca
  4. Pede ao Claude que gere:
       - Lista de TO-DOs priorizados para o dia
       - Pedidos a fazer a fornecedores (produtos/categorias em alta)
       - Clientes a abordar hoje
  5. Envia email via Outlook para tdcerqueira@worten.pt
"""

from __future__ import annotations

import sys
import json
import warnings
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────────────
_BASE = Path(__file__).parent
sys.path.insert(0, str(_BASE))

# ── Config ───────────────────────────────────────────────────────────────────
RECIPIENT_EMAIL = "tdcerqueira@worten.pt"
RECIPIENT_NAME  = "Tiago Cerqueira"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Recolha de dados
# ─────────────────────────────────────────────────────────────────────────────

def _get_boxmovers_context() -> dict:
    """Lê dados do BoxMovers Excel: PO activos + top categorias/marcas."""
    try:
        from boxmovers_reader import read_bm_deals, _get_bm_paths
        rows = read_bm_deals(year_filter=None)
        if not rows:
            return {}

        today = date.today()
        current_year = today.year

        # ── Deals PO (activos, não concluídos) ────────────────────────────
        po_rows = [r for r in rows if not r["concluded"] and r["status"].upper() not in ("CANCELADO",)]
        po_by_client: dict[str, list] = {}
        for r in po_rows:
            c = r["client"]
            po_by_client.setdefault(c, []).append(r)

        # ── Top categorias por receita (histórico concluído) ──────────────
        concluded = [r for r in rows if r["concluded"]]
        cat_rev: dict[str, float] = {}
        brand_rev: dict[str, float] = {}
        for r in concluded:
            cat   = r["cat"]
            brand = r["brand"]
            if cat and cat != "—":
                cat_rev[cat] = cat_rev.get(cat, 0) + r["revenue"]
            if brand and brand not in ("—", "SEM MARCA"):
                brand_rev[brand] = brand_rev.get(brand, 0) + r["revenue"]

        top_cats   = sorted(cat_rev.items(),   key=lambda x: x[1], reverse=True)[:8]
        top_brands = sorted(brand_rev.items(), key=lambda x: x[1], reverse=True)[:8]

        # ── Clientes com PO activo (resumo) ───────────────────────────────
        po_summary = []
        for client, deals in sorted(po_by_client.items()):
            total_rev = sum(d["revenue"] for d in deals)
            total_mg  = sum(d["mg_eur"]  for d in deals)
            brands    = list({d["brand"] for d in deals if d["brand"] != "—"})
            po_summary.append({
                "client":   client,
                "n_lines":  len(deals),
                "revenue":  round(total_rev, 0),
                "margin":   round(total_mg, 0),
                "brands":   brands[:5],
            })

        # ── Clientes que compraram no passado mas sem PO activo ───────────
        clients_with_history = {r["client"] for r in concluded}
        clients_with_po      = set(po_by_client.keys())
        dormant_clients = sorted(clients_with_history - clients_with_po)

        # ── Histórico mensal (últimos 6 meses) ────────────────────────────
        six_months_ago = (today - timedelta(days=180))
        monthly: dict[str, float] = {}
        for r in concluded:
            key = f"{r['year']}-{r['month']:02d}"
            if r["year"] > six_months_ago.year or (
                r["year"] == six_months_ago.year and r["month"] >= six_months_ago.month
            ):
                monthly[key] = monthly.get(key, 0) + r["revenue"]

        return {
            "po_active":        po_summary,
            "dormant_clients":  dormant_clients[:10],
            "top_categories":   [{"cat": c, "revenue_eur": round(v, 0)} for c, v in top_cats],
            "top_brands":       [{"brand": b, "revenue_eur": round(v, 0)} for b, v in top_brands],
            "monthly_trend":    dict(sorted(monthly.items())),
            "total_po_value":   round(sum(s["revenue"] for s in po_summary), 0),
            "n_po_clients":     len(po_by_client),
        }
    except Exception as e:
        print(f"[daily_briefing] BoxMovers error: {e}")
        traceback.print_exc()
        return {}


def _get_supabase_pipeline() -> dict:
    """Lê pipeline do Supabase (deals da cotacao_agent app)."""
    try:
        from deal_tracker import get_pipeline_stats, list_deals
        from config import PIPELINE_ACTIVE_STATUSES, PIPELINE_CLOSED_STATUSES

        deals = list_deals()
        if not deals:
            return {}

        today_str = date.today().isoformat()
        stale_threshold = (date.today() - timedelta(days=14)).isoformat()

        active, stale, won_30d = [], [], []
        for d in deals:
            status = d.get("Status", "")
            upd    = str(d.get("Data Último Update", "") or "")[:10]
            if status in PIPELINE_ACTIVE_STATUSES:
                active.append(d)
                if upd and upd < stale_threshold:
                    stale.append(d)
            if status in ("Faturado", "Concluído") and upd >= (date.today() - timedelta(days=30)).isoformat():
                won_30d.append(d)

        def _fmt(d):
            return {
                "id":      d.get("Deal ID", "—"),
                "client":  d.get("Cliente", "—"),
                "status":  d.get("Status", "—"),
                "value":   d.get("Valor Proposta (€)", 0) or 0,
                "updated": str(d.get("Data Último Update", ""))[:10],
                "products": str(d.get("Produtos", ""))[:80],
            }

        return {
            "active_deals":  [_fmt(d) for d in active[:15]],
            "stale_deals":   [_fmt(d) for d in stale[:10]],
            "won_last_30d":  [_fmt(d) for d in won_30d[:5]],
            "n_active":      len(active),
            "n_stale":       len(stale),
            "pipeline_value": round(sum(
                float(d.get("Valor Proposta (€)", 0) or 0) for d in active
            ), 0),
        }
    except Exception as e:
        print(f"[daily_briefing] Supabase error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Geração do briefing com Claude
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """És o assistente comercial de Tiago Cerqueira, Export Manager B2B da Worten (BoxMovers / TDC).
Tens acesso a dados reais de deals, pipeline e histórico de vendas.

CRÍTICO: Responde EXCLUSIVAMENTE com HTML válido. NUNCA uses Markdown.
- PROIBIDO: ##, **, *, |---|, backticks, --- separators
- OBRIGATÓRIO: usa <h2>, <h3>, <ul>, <li>, <table>, <b>, <span> etc.
- O output vai ser injectado directamente num email HTML. Markdown quebra o formato.

Gera um briefing diário CONCISO e ACCIONÁVEL em Português de Portugal.
Tom: profissional, directo, sem rodeios. Usa emojis com moderação.

Estrutura obrigatória em HTML:

<h2>📋 TO-DOs DO DIA</h2>
Tabela com colunas: #, Tarefa, Urgência (Alta🔴/Média🟡/Baixa🟢). Máx 8 itens.

<h2>🏭 PEDIDOS A FORNECEDORES</h2>
Tabela com colunas: Marca/Categoria, Acção, Justificação. Com base nas categorias/marcas mais vendidas.

<h2>👥 CLIENTES A ABORDAR HOJE</h2>
Tabela com colunas: Cliente, Razão para contacto. Clientes dormentes ou com oportunidade concreta.

<h2>⚡ ALERTAS</h2>
Lista de alertas: deals estagnados, quedas de receita, oportunidades urgentes.

Sê específico: usa nomes reais de clientes, marcas e categorias dos dados fornecidos.
Não inventes dados que não estejam no contexto."""

def _generate_briefing(bm: dict, sb: dict) -> str:
    """Chama Claude API para gerar o briefing em HTML."""
    try:
        import anthropic
        from config import _get_secret

        api_key = _get_secret("ANTHROPIC_API_KEY")
        client  = anthropic.Anthropic(api_key=api_key)

        today = date.today().strftime("%A, %d de %B de %Y")

        context = {
            "data":             today,
            "boxmovers":        bm,
            "pipeline_app":     sb,
        }

        user_msg = f"""Dados de hoje ({today}):

{json.dumps(context, ensure_ascii=False, indent=2)}

INSTRUÇÕES DE OUTPUT:
- Responde APENAS com HTML puro — zero Markdown (sem ##, **, |---|, backticks)
- Começa directamente com uma linha de resumo em <p>: receita PO activa total e nº de clientes
- Segue a estrutura de 4 secções com tabelas HTML
- Não incluas <html>, <head>, <body> — só o conteúdo interno"""

        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return msg.content[0].text

    except Exception as e:
        print(f"[daily_briefing] Claude API error: {e}")
        traceback.print_exc()
        # Fallback: briefing básico sem IA
        return _fallback_briefing(bm, sb)


def _fallback_briefing(bm: dict, sb: dict) -> str:
    """Briefing básico (sem IA) como fallback."""
    today = date.today().strftime("%d/%m/%Y")
    lines = [f"<h2>📋 Briefing Diário — {today}</h2>"]

    if bm:
        lines.append(f"<p><b>PO Activos:</b> {bm.get('n_po_clients',0)} clientes · €{bm.get('total_po_value',0):,.0f}</p>")
        lines.append("<h3>Deals PO em Aberto:</h3><ul>")
        for po in bm.get("po_active", []):
            lines.append(f"<li><b>{po['client']}</b> — {po['n_lines']} linhas · €{po['revenue']:,.0f} · {', '.join(po['brands'])}</li>")
        lines.append("</ul>")

    if sb:
        lines.append(f"<h3>Pipeline App ({sb.get('n_active',0)} deals activos):</h3><ul>")
        for d in sb.get("stale_deals", []):
            lines.append(f"<li>⚠️ <b>{d['client']}</b> [{d['id']}] — sem update desde {d['updated']}</li>")
        lines.append("</ul>")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Envio via Resend (fiável em modo automatizado, sem dependência do Outlook)
# ─────────────────────────────────────────────────────────────────────────────

_EMAIL_WRAPPER = """
<html><body style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1a1a2e;max-width:700px;margin:auto;padding:16px;">
  <div style="background:linear-gradient(135deg,#1B2744,#2a3a6e);color:#fff;padding:18px 24px;border-radius:8px 8px 0 0;">
    <span style="font-size:11px;letter-spacing:2px;opacity:.7;display:block;">TRANSGLOBAL DISTRIBUTION CHAIN</span>
    <span style="font-size:20px;font-weight:700;">Daily Business Briefing</span>
    <span style="font-size:12px;opacity:.8;float:right;margin-top:-18px;">{date}</span>
  </div>
  <div style="background:#fff;padding:24px;border:1px solid #e2e8f0;border-top:3px solid #C49A3C;border-radius:0 0 8px 8px;">
    {body}
  </div>
  <p style="font-size:11px;color:#aaa;text-align:center;margin-top:10px;">
    Gerado por BoxMovers AI · responde a este email para feedback
  </p>
</body></html>"""


def _send_email(subject: str, html_body: str) -> bool:
    """Envia via Resend SDK (mesma infra que a cotacao_agent app)."""
    try:
        import resend
        from config import _get_secret, SENDER_EMAIL, USER_EMAIL

        resend.api_key = _get_secret("RESEND_API_KEY")

        full_html = _EMAIL_WRAPPER.format(
            date=date.today().strftime("%d/%m/%Y"),
            body=html_body,
        )

        params = {
            "from":     f"BoxMovers AI <{SENDER_EMAIL}>",
            "to":       [RECIPIENT_EMAIL],
            "subject":  subject,
            "html":     full_html,
            "reply_to": USER_EMAIL,
        }
        result = resend.Emails.send(params)
        email_id = result.get("id") if hasattr(result, "get") else getattr(result, "id", None)
        print(f"[daily_briefing] Email enviado | id={email_id}")
        return True

    except Exception as e:
        print(f"[daily_briefing] Resend error: {e}")
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    today     = date.today()
    weekday   = today.weekday()   # 0=Segunda, 6=Domingo

    # Não enviar ao fim de semana
    if weekday >= 5:
        print(f"[daily_briefing] Fim de semana ({today}), a ignorar.")
        return

    print(f"[daily_briefing] A gerar briefing para {today}...")

    # 1. Recolher dados
    bm_data = _get_boxmovers_context()
    sb_data = _get_supabase_pipeline()

    if not bm_data and not sb_data:
        print("[daily_briefing] Sem dados disponíveis. A abortar.")
        return

    # 2. Gerar briefing com Claude
    html_content = _generate_briefing(bm_data, sb_data)

    # 3. Enviar
    day_names_pt = {0:"Segunda",1:"Terça",2:"Quarta",3:"Quinta",4:"Sexta"}
    subject = f"[BoxMovers] Briefing {day_names_pt.get(weekday,'')} {today.strftime('%d/%m')} — {bm_data.get('n_po_clients',0)} PO activos · €{bm_data.get('total_po_value',0):,.0f}"

    sent = _send_email(subject, html_content)
    if not sent:
        # Fallback: guardar em ficheiro se email falhar
        out_path = _BASE / f"briefings/briefing_{today.isoformat()}.html"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(f"<html><body>{html_content}</body></html>", encoding="utf-8")
        print(f"[daily_briefing] Email falhou | guardado em {out_path}")


if __name__ == "__main__":
    main()
