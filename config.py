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

# ── Email SMTP ─────────────────────────────────────────────────────────────────
SMTP_EMAIL    = _get_secret("SMTP_EMAIL",    "tiago.cerqueira@transglobalchain.com")
SMTP_PASSWORD = _get_secret("SMTP_PASSWORD", "")
SMTP_HOST     = _get_secret("SMTP_HOST",     "smtp.gmail.com")
SMTP_PORT     = int(_get_secret("SMTP_PORT", "587"))

# ── Paths (usados apenas em modo local) ───────────────────────────────────────
BASE_DIR  = Path(__file__).parent.parent
DEALS_FILE = BASE_DIR / "Deals_Tracking.xlsx"   # fallback local

# Simulador — só necessário para rebuild do cache local
_SHORTCUT = BASE_DIR / "Docs" / "Simulador_AfricanMarkets - Atalho.lnk"

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

try:
    SIMULATOR_FILE = _resolve_shortcut(_SHORTCUT)
except Exception:
    SIMULATOR_FILE = _SHORTCUT

CACHE_DIR       = Path(__file__).parent / ".cache"
SIMULATOR_CACHE = CACHE_DIR / "simulator_index.json"
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
    "Rascunho",
    "Enviado",
    "Em Negociação",
    "Follow-up",
    "Fechado",
    "Perdido",
]

STATUS_COLORS = {
    "Rascunho":      "FFF3CD",
    "Enviado":       "D1ECF1",
    "Em Negociação": "D4EDDA",
    "Follow-up":     "FFE5CC",
    "Fechado":       "C3E6CB",
    "Perdido":       "F5C6CB",
}
