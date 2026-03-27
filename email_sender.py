"""
Email Sender — Envio via Resend API
=====================================
Usa a API HTTP do Resend para enviar emails.
Compatível com Railway e outros ambientes cloud (sem restrições SMTP).
"""

import urllib.request
import urllib.error
import json

from config import RESEND_API_KEY, SENDER_EMAIL, USER_EMAIL, COMPANY_NAME


def send_email(
    to: str,
    subject: str,
    html_body: str,
    reply_to: str = None,
    cc: list = None,
) -> tuple[bool, str]:
    """
    Envia email HTML via Resend API.

    Returns:
        (True, "") em caso de sucesso
        (False, mensagem_erro) em caso de erro
    """
    if not RESEND_API_KEY:
        return False, "RESEND_API_KEY não configurado. Adiciona-a nas variáveis do Railway."

    recipients = [r.strip() for r in to.split(";") if r.strip()]
    if not recipients:
        return False, "Nenhum endereço de email válido."

    payload = {
        "from": f"Tiago Cerqueira <{SENDER_EMAIL}>",
        "to":   recipients,
        "subject": subject,
        "html": html_body,
        "text": "Por favor consulte a versão HTML deste email.",
        "reply_to": reply_to or USER_EMAIL,
    }
    if cc:
        payload["cc"] = cc

    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            "https://api.resend.com/emails",
            data=data,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type":  "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 201):
                return True, ""
            body = resp.read().decode("utf-8")
            return False, f"Resend HTTP {resp.status}: {body}"

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        # Mostra o corpo completo para debug
        return False, f"Resend erro (key={RESEND_API_KEY[:8]}...): {body}"
    except Exception as e:
        return False, f"Erro: {e}"


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
