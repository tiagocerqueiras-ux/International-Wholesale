"""
Cotação Agent — Configurações
International Wholesale | Worten
Cloud-ready: lê credenciais de st.secrets (Streamlit Cloud) ou .env (local)
"""

import os
from pathlib import Path

# ── Secrets: st.secrets (cloud) → .env → variável de ambiente ─────────────────
def _get_secret(key: str, default: str = "") -> str:
    # 1. st.secrets (Streamlit Cloud ou app Streamlit local)
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val is not None:
            return str(val)
    except Exception:
        pass

    # 2. Ler secrets.toml directamente (scripts standalone)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            tomllib = None

    if tomllib:
        toml_path = Path(__file__).parent / ".streamlit" / "secrets.toml"
        if toml_path.exists():
            try:
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)
                val = data.get(key)
                if val is not None:
                    return str(val)
            except Exception:
                pass

    # 3. Fallback para .env local
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent / "email_agent" / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
        else:
            load_dotenv(override=False)
    except ImportError:
        pass

    return os.getenv(key, default)


# ── API ────────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
CLAUDE_MODEL      = "claude-sonnet-4-6"

# ── Supabase ───────────────────────────────────────────────────────────────────
SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_KEY")

# ── Email (Resend API) ─────────────────────────────────────────────────────────
RESEND_API_KEY  = _get_secret("RESEND_API_KEY", "")
SENDER_EMAIL    = _get_secret("SMTP_EMAIL", "tiago.cerqueira@transglobalchain.com")

# Emails internos para alertas de fecho de deal
STOCKS_EMAIL = _get_secret("STOCKS_EMAIL", "")
ADMIN_EMAIL  = _get_secret("ADMIN_EMAIL",  "")

# ── Paths (usados apenas em modo local) ───────────────────────────────────────
BASE_DIR  = Path(__file__).parent.parent
DEALS_FILE = BASE_DIR / "Deals_Tracking.xlsx"   # fallback local

# Simulador — usado apenas no rebuild local da cache de SKUs.
# Em cloud (Railway) nenhum destes caminhos existe; a app usa o
# simulator_index.json.gz empacotado no repositório.
_SIMULATOR_SHORTCUT = BASE_DIR / "Docs" / "Simulador_AfricanMarkets - Atalho.lnk"


def _resolve_shortcut(lnk_path: Path) -> Path:
    """Resolve atalho Windows .lnk — só funciona em Windows com pywin32."""
    try:
        import win32com.client
        sh  = win32com.client.Dispatch("WScript.Shell")
        lnk = sh.CreateShortcut(str(lnk_path))
        target = Path(lnk.TargetPath)
        if target.exists():
            return target
    except Exception:
        pass
    return lnk_path


def _resolve_simulator_file() -> Path:
    """Localiza o Simulador_AfricanMarkets.xlsx por ordem de prioridade, sem
    depender do atalho .lnk nem do win32com:
      1. Override manual via secret/env SIMULATOR_PATH
      2. Biblioteca SharePoint/OneDrive sincronizada do utilizador
      3. Cópia local em Docs/
      4. Atalho .lnk (legado, se existir e win32com disponível)
    """
    override = _get_secret("SIMULATOR_PATH", "")
    if override:
        return Path(override)

    candidates = [
        Path.home() / "Worten" / "INC - BI & Analytics - Documents"
            / "4. B2B" / "6. Franchising" / "Simulador_AfricanMarkets.xlsx",
        BASE_DIR / "Docs" / "Simulador_AfricanMarkets.xlsx",
    ]
    if _SIMULATOR_SHORTCUT.exists():
        candidates.append(_resolve_shortcut(_SIMULATOR_SHORTCUT))

    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    # Default documentado (caminho de rede), mesmo que ausente nesta máquina/cloud
    return candidates[0]


SIMULATOR_FILE = _resolve_simulator_file()

CACHE_DIR       = Path(__file__).parent / ".cache"
SIMULATOR_CACHE = CACHE_DIR / "simulator_index.json"
TRANSPORT_FILE  = BASE_DIR / "Docs" / "Simulador_Exportacao_V4.26 - B2B.xlsx"
# transport_cache em pasta commitada (Railway não tem Excel local)
TRANSPORT_CACHE = Path(__file__).parent / "data" / "transport_cache.json"
EMAILS_OUT_DIR  = Path(__file__).parent / "emails_out"

# ── Simulador ─────────────────────────────────────────────────────────────────
ENTITY_FILTER   = {"701", "708"}
ENTITY_PRIORITY = ["708", "701"]
SIMULATOR_HEADER_ROW = 5

SIMULATOR_COLS = {
    "sku_id":    2,
    "ean":       3,
    "name":      4,
    "status":    5,
    "entity":    6,
    "cat":       8,
    "subcat":    9,
    "brand":     12,
    "pvp_pt":    13,
    "stock":     14,
    "pcl":       15,
    "eis_total": 16,
    "eis_da":    17,
    "eis_reee":  18,
    "cgf_reb":   22,
    "cgf_com":   23,
    "sell_in":   29,
    "sell_out":  30,
    "unit_cost": 34,
}

# ── Identidade comercial ───────────────────────────────────────────────────────
USER_NAME    = "Tiago Cerqueira"
USER_TITLE   = "International Wholesale"
USER_EMAIL   = "tdcerqueira@worten.pt"
USER_PHONE   = "+351 919 540 175"
COMPANY_NAME = "International Wholesale | Worten"
WAREHOUSE    = "EN3 Km7 Arneiro, 2050-306 Azambuja, Portugal"
INCOTERM     = "EXW — Ex Works (Azambuja)"

# ── Incoterms 2020 ────────────────────────────────────────────────────────────
INCOTERMS_LIST = [
    "EXW — Ex Works (Azambuja)",
    "FCA — Free Carrier",
    "FAS — Free Alongside Ship",
    "FOB — Free On Board",
    "CFR — Cost and Freight",
    "CIF — Cost Insurance and Freight",
    "CPT — Carriage Paid To",
    "CIP — Carriage and Insurance Paid To",
    "DAP — Delivered At Place",
    "DPU — Delivered at Place Unloaded",
    "DDP — Delivered Duty Paid",
]

# ── Condições de pagamento ────────────────────────────────────────────────────
PAYMENT_CONDITIONS_LIST = [
    "100% Pré-Pagamento — wire transfer (T/T)",
    "Pronto Pagamento — no momento da encomenda",
    "Pronto Pagamento — com 2% desconto financeiro",
    "COD — Pagamento Contra Entrega",
    "15 dias data fatura",
    "30 dias data fatura",
    "45 dias data fatura",
    "60 dias data fatura",
    "90 dias data fatura",
    "30 dias Fim do Mês (DFM)",
    "60 dias Fim do Mês (DFM)",
    "Faseado: 30% adjudicação + 40% entrega + 30% aceitação",
    "Faseado: 50% adiantamento + 50% entrega",
    "Faseado: 30% adjudicação + 70% entrega",
    "Por marcos / milestones (acordo prévio)",
    "Conta Corrente / Linha de Crédito aprovada",
    "Comissão sobre margem / pagamento por sucesso",
    "Rappel / Rebate posterior por volume",
    "Outra (personalizada)...",
]
PAYMENT_CONDITIONS_DEFAULT = PAYMENT_CONDITIONS_LIST[0]

# ── Status dos deals ──────────────────────────────────────────────────────────
STATUSES = [
    "Lead",
    "Pedido de Cotação",
    "Rascunho",
    "Enviado",
    "Em Negociação",
    "Follow-up",
    "Encomenda Confirmada",
    "Em Preparação",
    "Expedido",
    "Entregue",
    "Faturado",
    "Arquivado",
    "Perdido",
]

STATUS_COLORS = {
    "Lead":                 "E8F4FD",
    "Pedido de Cotação":    "D0E8F7",
    "Rascunho":             "FFF3CD",
    "Enviado":              "D1ECF1",
    "Em Negociação":        "D4EDDA",
    "Follow-up":            "FFE5CC",
    "Encomenda Confirmada": "C8E6C9",
    "Em Preparação":        "DCEDC8",
    "Expedido":             "F3E5F5",
    "Entregue":             "E1F5FE",
    "Faturado":             "C3E6CB",
    "Arquivado":            "E0E0E0",
    "Perdido":              "F5C6CB",
}

# ── Pipeline — grupos de status ───────────────────────────────────────────────
PIPELINE_ACTIVE_STATUSES = [
    "Lead", "Pedido de Cotação", "Rascunho", "Enviado",
    "Em Negociação", "Follow-up",
]
PIPELINE_ORDER_STATUSES = [
    "Encomenda Confirmada", "Em Preparação", "Expedido", "Entregue",
]
PIPELINE_CLOSED_STATUSES = ["Faturado", "Arquivado", "Perdido"]

# Days without update before a deal is flagged as "at risk"
DEAL_STALE_DAYS = 14

# ── Pricing Engine ────────────────────────────────────────────────────────────
MIN_MARGIN_DEFAULT = 3.0   # % — alerta visual quando margem por linha desce abaixo deste valor
TARGET_MARGIN_DEFAULT = 5.0  # % — margem alvo global para cálculo de Apoio Adicional no RFQ

# ── Business Plan — KPIs de referência ────────────────────────────────────────
BP_TARGET_REVENUE   = 15_000_000   # EUR/ano — faturação alvo
BP_BREAK_EVEN       = 11_500_000   # EUR/ano — ponto de equilíbrio
BP_TARGET_EBITDA    =    100_000   # EUR/ano — EBITDA alvo
BP_TAKE_RATE        =      0.0265  # 2,65% sobre faturação = nossa parte
BP_OUR_CUT_PCT      =       0.30   # 30% da margem bruta = proveito TSVR Partners (legado BP)
BP_FIXED_COSTS      =    306_000   # EUR/ano — pessoal fixo (2 colabs + 2 contractors)
BP_SCENARIO_BASE    = 20_000_000   # EUR — cenário base
BP_SCENARIO_OPT     = 30_000_000   # EUR — cenário otimista

# ── Estrutura de Comissões — Contrato em vigor (início Abril 2025) ─────────────
# Fórmula: Proveito = MG real × taxa_comissão(T/O acumulado ano contratual)
# Ano contratual: Abr → Mar  |  Base: 17,5%  |  Máx: 27,5%
BP_MGN_WRT_ESTIM       = 0.030   # 3,0% — margem bruta Worten estimada (BP)
BP_COMMISSION_BASE_PCT = 0.175   # 17,5% — comissão base sobre a margem real

# Aceleradores sobre T/O acumulado do ano contratual (Abr→Mar)
# Cada entrada: (to_min_eur, to_max_eur_excl, pct_extra_sobre_base)
BP_COMMISSION_TIERS = [
    (             0,  9_999_999, 0.000),   # Base: 17,5%
    (10_000_000, 14_999_999,    0.025),   # +2,5% → 20,0%
    (15_000_000, 19_999_999,    0.050),   # +5,0% → 22,5%
    (20_000_000, 24_999_999,    0.075),   # +7,5% → 25,0%
    (25_000_000, float("inf"), 0.100),   # +10,0% → 27,5% (máximo contratual)
]

# Comissão anual estimada por escalão (referência do BP)
BP_COMMISSION_TIER_CAPS = {
    "base":   52_500,   # < 10M T/O
    "tier1":  90_000,   # 10–15M T/O
    "tier2": 135_000,   # 15–20M T/O
    "tier3": 168_750,   # 20–25M T/O
    "tier4": 206_250,   # > 25M T/O
}

def bp_commission_rate(annual_turnover: float) -> float:
    """Devolve a taxa total de comissão (base + acelerador) para o T/O do ano contratual."""
    extra = 0.0
    for to_min, to_max, pct_extra in BP_COMMISSION_TIERS:
        if annual_turnover >= to_min:
            extra = pct_extra
    return BP_COMMISSION_BASE_PCT + extra

def bp_proveito(annual_turnover: float) -> float:
    """Calcula o proveito TSVR Partners estimado: T/O × 3% margem WRT × taxa_comissão."""
    return annual_turnover * BP_MGN_WRT_ESTIM * bp_commission_rate(annual_turnover)

def bp_commission_tier_name(annual_turnover: float) -> str:
    """Devolve o nome do escalão activo para o T/O dado."""
    if annual_turnover >= 25_000_000: return "🟣 Acel +10,0% → 27,5%  (>25M)"
    if annual_turnover >= 20_000_000: return "🔴 Acel  +7,5% → 25,0%  (20–25M)"
    if annual_turnover >= 15_000_000: return "🟠 Acel  +5,0% → 22,5%  (15–20M)"
    if annual_turnover >= 10_000_000: return "🟡 Acel  +2,5% → 20,0%  (10–15M)"
    return "⚪ Base 17,5%  (<10M)"
