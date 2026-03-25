"""
Email Sender — Envio via SMTP (Gmail / Google Workspace)
=========================================================
Substitui outlook_sender.py para ambientes cloud.
Compatível com Gmail App Passwords e Google Workspace.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_EMAIL, SMTP_PASSWORD, SMTP_HOST, SMTP_PORT, USER_EMAIL


def send_email(
    to: str,
    subject: str,
    html_body: str,
    reply_to: str = None,
    cc: list = None,
) -> tuple[bool, str]:
    """
    Envia email HTML via SMTP.

    Returns:
        (True, "") em caso de sucesso
        (False, mensagem_erro) em caso de erro
    """
    if not SMTP_PASSWORD:
        return False, "SMTP_PASSWORD não configurado. Verifica os secrets."

    # Suporta múltiplos destinatários separados por ";"
    recipients = [r.strip() for r in to.split(";") if r.strip()]
    if not recipients:
        return False, "Nenhum endereço de email válido."

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"International Wholesale | Worten <{SMTP_EMAIL}>"
        msg["To"]      = ", ".join(recipients)
        msg["Reply-To"] = reply_to or USER_EMAIL
        if cc:
            msg["Cc"] = ", ".join(cc)
            recipients += cc

        # Versão plain text mínima (fallback)
        plain = "Por favor consulte a versão HTML deste email."
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html",  "utf-8"))

        # Gmail App Passwords funcionam com ou sem espaços — normalizar
        _pwd = SMTP_PASSWORD.replace(" ", "")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_EMAIL, _pwd)
            server.sendmail(SMTP_EMAIL, recipients, msg.as_string())

        return True, ""

    except smtplib.SMTPAuthenticationError:
        return False, (
            "Erro de autenticação SMTP. "
            "Confirma o App Password em myaccount.google.com/security."
        )
    except smtplib.SMTPException as e:
        return False, f"Erro SMTP: {e}"
    except Exception as e:
        return False, f"Erro: {e}"


# Alias para retrocompatibilidade com chamadas create_draft em app.py
def create_draft(to: str, subject: str, html_body: str, send: bool = False) -> tuple[bool, str]:
    """
    Wrapper de compatibilidade: na versão cloud envia sempre (não há rascunhos Outlook).
    O parâmetro send é ignorado — o email é sempre enviado via SMTP.
    """
    return send_email(to=to, subject=subject, html_body=html_body)


def build_subject(deal_id: str, client_name: str, language: str = "EN") -> str:
    templates = {
        "EN": f"Commercial Proposal — {deal_id} | {client_name}",
        "PT": f"Proposta Comercial — {deal_id} | {client_name}",
        "ES": f"Propuesta Comercial — {deal_id} | {client_name}",
        "FR": f"Proposition Commerciale — {deal_id} | {client_name}",
    }
    return templates.get(language.upper(), templates["EN"])
