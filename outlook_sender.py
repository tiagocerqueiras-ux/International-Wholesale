"""
Outlook Sender — Criação de rascunho / envio via Outlook (win32com)
"""

from pathlib import Path


def create_draft(to: str, subject: str, html_body: str, send: bool = False) -> tuple[bool, str]:
    """
    Cria um rascunho no Outlook (ou envia diretamente se send=True).
    Inicializa o COM explicitamente para compatibilidade com threads do Streamlit.

    Returns:
        (True, "") se bem-sucedido
        (False, mensagem_erro) em caso de erro
    """
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()   # obrigatório em threads secundárias (Streamlit)
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)   # 0 = olMailItem
            mail.To       = to
            mail.Subject  = subject
            mail.HTMLBody = html_body
            if send:
                mail.Send()
            else:
                mail.Save()
                mail.Display()
            return True, ""
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:
        msg = str(e)
        print(f"[outlook_sender] Erro: {msg}")
        return False, msg


def build_subject(deal_id: str, client_name: str, language: str = "EN", company: str = "") -> str:
    recipient = f"{company} - {client_name}" if company and company.strip() else client_name
    templates = {
        "EN": f"Commercial Proposal — {deal_id} | {recipient}",
        "PT": f"Proposta Comercial — {deal_id} | {recipient}",
        "ES": f"Propuesta Comercial — {deal_id} | {recipient}",
        "FR": f"Proposition Commerciale — {deal_id} | {recipient}",
    }
    return templates.get(language.upper(), templates["EN"])
