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

Gera um briefing diário CONCISO e ACCIONÁVEL em Português de Portugal.
Tom: profissional, directo, sem rodeios. Usa emojis com moderação.

Estrutura obrigatória (HTML para email):
1. 📋 TO-DOs DO DIA — lista priorizada (máx 8 itens), cada um com [URGÊNCIA: Alta/Média/Baixa]
2. 🏭 PEDIDOS A FORNECEDORES — com base nas categorias/marcas mais procuradas, o que pedir/negociar
3. 👥 CLIENTES A ABORDAR HOJE — clientes dormentes ou com oportunidade identificada, com razão concreta
4. ⚡ ALERTAS — deals estagnados, oportunidades a não perder

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

```json
{json.dumps(context, ensure_ascii=False, indent=2)}
```

Gera o briefing diário completo em HTML (sem <html>/<body>, só o conteúdo interno).
Inclui uma linha de resumo no início: receita PO activa total e nº de clientes com deals em aberto."""

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
# 3. Envio via Outlook
# ─────────────────────────────────────────────────────────────────────────────

def _send_outlook(subject: str, html_body: str) -> bool:
    """Envia email via Outlook COM (Python win32com)."""
    try:
        import win32com.client as wc
        outlook = wc.Dispatch("outlook.application")
        mail    = outlook.CreateItem(0)

        mail.To          = RECIPIENT_EMAIL
        mail.Subject     = subject
        mail.HTMLBody    = f"""
<html><body style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1a1a2e;max-width:700px;margin:auto;">
  <div style="background:linear-gradient(135deg,#1B2744,#2a3a6e);color:#fff;padding:18px 24px;border-radius:8px 8px 0 0;">
    <span style="font-size:11px;letter-spacing:2px;opacity:.7;">TRANSGLOBAL DISTRIBUTION CHAIN</span><br>
    <span style="font-size:20px;font-weight:700;">Daily Business Briefing</span>
  </div>
  <div style="background:#fff;padding:24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">
    {html_body}
  </div>
  <p style="font-size:11px;color:#999;text-align:center;margin-top:12px;">
    Gerado automaticamente por BoxMovers AI · {date.today().strftime('%d/%m/%Y')}
  </p>
</body></html>"""

        mail.Send()
        print(f"[daily_briefing] Email enviado para {RECIPIENT_EMAIL}")
        return True

    except Exception as e:
        print(f"[daily_briefing] Outlook error: {e}")
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

    sent = _send_outlook(subject, html_content)
    if not sent:
        # Fallback: guardar em ficheiro se email falhar
        out_path = _BASE / f"briefings/briefing_{today.isoformat()}.html"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(f"<html><body>{html_content}</body></html>", encoding="utf-8")
        print(f"[daily_briefing] Email falhou → guardado em {out_path}")


if __name__ == "__main__":
    main()
