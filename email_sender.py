"""
Email Sender — Envio via Resend SDK
=====================================
Usa o SDK oficial do Resend para enviar emails.
Compatível com Railway e outros ambientes cloud (sem restrições SMTP).
"""

import resend

from config import RESEND_API_KEY, SENDER_EMAIL, USER_EMAIL, COMPANY_NAME


def send_email(
    to: str,
    subject: str,
    html_body: str,
    reply_to: str = None,
    cc: list = None,
) -> tuple[bool, str]:
    """
    Envia email HTML via Resend SDK.

    Returns:
        (True, "") em caso de sucesso
        (False, mensagem_erro) em caso de erro
    """
    if not RESEND_API_KEY:
        return False, "RESEND_API_KEY não configurado. Adiciona-a nas variáveis do Railway."

    recipients = [r.strip() for r in to.split(";") if r.strip()]
    if not recipients:
        return False, "Nenhum endereço de email válido."

    resend.api_key = RESEND_API_KEY

    params: resend.Emails.SendParams = {
        "from": f"Tiago Cerqueira <{SENDER_EMAIL}>",
        "to":   recipients,
        "subject": subject,
        "html": html_body,
        "reply_to": reply_to or USER_EMAIL,
    }
    if cc:
        params["cc"] = cc

    try:
        result = resend.Emails.send(params)
        # SDK retorna dict com "id" em caso de sucesso
        if result and result.get("id"):
            return True, ""
        return False, f"Resend: resposta inesperada: {result}"
    except Exception as e:
        return False, f"Resend erro: {e}"


# Alias para compatibilidade com chamadas create_draft em app.py
def create_draft(to: str, subject: str, html_body: str, send: bool = False) -> tuple[bool, str]:
    return send_email(to=to, subject=subject, html_body=html_body)


def build_subject(deal_id: str, client_name: str, language: str = "EN") -> str:
    templates = {
        "EN": f"Commercial Proposal — {deal_id} | {client_name}",
        "PT": f"Proposta Comercial — {deal_id} | {client_name}",
        "ES": f"Propuesta Comercial — {deal_id} | {client_name}",
        "FR": f"Proposition Commerciale — {deal_id} | {client_name}",
    }
    return templates.get(language.upper(), templates["EN"])
