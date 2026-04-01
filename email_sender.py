"""
Email Sender — Envio com fallback inteligente
==============================================
1. RESEND_API_KEY configurado  → Resend SDK  (funciona em cloud/Railway)
2. Windows + Outlook instalado → Outlook COM (funciona localmente)
3. Nenhum disponível           → devolve (False, msg) + HTML para download

RESEND_API_KEY: configura em Railway → Variables ou secrets.toml
"""

import platform
import sys

from config import RESEND_API_KEY, SENDER_EMAIL, USER_EMAIL, COMPANY_NAME


# ── 1. Envio via Resend SDK ───────────────────────────────────────────────────

def _send_via_resend(
    to: str,
    subject: str,
    html_body: str,
    reply_to: str = None,
    cc: list = None,
    bcc: list = None,
) -> tuple[bool, str]:
    try:
        import resend
    except ImportError:
        return False, "resend SDK não instalado (pip install resend)"

    recipients = [r.strip() for r in to.split(";") if r.strip()]
    if not recipients:
        return False, "Nenhum endereço de email válido."

    resend.api_key = RESEND_API_KEY

    params = {
        "from":     f"Tiago Cerqueira <{SENDER_EMAIL}>",
        "to":       recipients,
        "subject":  subject,
        "html":     html_body,
        "reply_to": reply_to or USER_EMAIL,
    }
    if cc:  params["cc"]  = cc
    if bcc: params["bcc"] = bcc

    try:
        result = resend.Emails.send(params)
        # SDK >= 2.x → Email object com .id; SDK 1.x → dict com "id"
        email_id = getattr(result, "id", None) or (
            result.get("id") if isinstance(result, dict) else None
        )
        if email_id:
            return True, ""
        return False, f"Resend: resposta inesperada: {result}"
    except Exception as e:
        return False, f"Resend erro: {e}"


# ── 2. Envio via Outlook COM (Windows) ────────────────────────────────────────

def _send_via_outlook(
    to: str,
    subject: str,
    html_body: str,
) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Outlook COM apenas disponível em Windows"
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.To       = to
            mail.Subject  = subject
            mail.HTMLBody = html_body
            mail.Send()
            return True, ""
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        return False, f"Outlook COM erro: {e}"


# ── Interface pública ─────────────────────────────────────────────────────────

def send_email(
    to: str,
    subject: str,
    html_body: str,
    reply_to: str = None,
    cc: list = None,
    bcc: list = None,
) -> tuple[bool, str]:
    """
    Tenta enviar pelo melhor método disponível.
    Devolve (True, "") em caso de sucesso ou (False, msg_erro) em falha.
    """
    # --- Resend (cloud-first) ---
    if RESEND_API_KEY:
        ok, err = _send_via_resend(to, subject, html_body, reply_to, cc, bcc)
        if ok:
            return True, ""
        # Se falhou por razão transitória, não tenta Outlook
        return False, f"Resend: {err}"

    # --- Outlook COM (local Windows) ---
    if platform.system() == "Windows":
        ok, err = _send_via_outlook(to, subject, html_body)
        if ok:
            return True, "Enviado via Outlook"
        return False, f"Outlook: {err}"

    # --- Nenhum método disponível ---
    return False, (
        "Envio automático não configurado.\n"
        "• Para ativar na cloud: adiciona RESEND_API_KEY nas variáveis do Railway.\n"
        "• Para uso local: instala o Outlook no Windows.\n"
        "Usa o botão 'Download HTML' para enviar manualmente."
    )


# Alias para compatibilidade com app.py
def create_draft(
    to: str,
    subject: str,
    html_body: str,
    send: bool = False,
    cc: list = None,
    bcc: list = None,
) -> tuple[bool, str]:
    return send_email(to=to, subject=subject, html_body=html_body, cc=cc, bcc=bcc)


def build_subject(deal_id: str, client_name: str, language: str = "EN", company: str = "") -> str:
    recipient = f"{company} - {client_name}" if company and company.strip() else client_name
    templates = {
        "EN": f"Commercial Proposal \u2014 {deal_id} | {recipient}",
        "PT": f"Proposta Comercial \u2014 {deal_id} | {recipient}",
        "ES": f"Propuesta Comercial \u2014 {deal_id} | {recipient}",
        "FR": f"Proposition Commerciale \u2014 {deal_id} | {recipient}",
    }
    return templates.get(language.upper(), templates["EN"])
