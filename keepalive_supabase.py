"""
keepalive_supabase.py — mantém o projeto Supabase (plano Free) ativo
====================================================================
O plano Free pausa projetos com >7 dias sem atividade. Esta é a BD de PRODUÇÃO,
por isso corremos 1 query trivial por dia (via tarefa agendada) para o "relógio"
dos 7 dias nunca chegar ao fim → o projeto nunca pausa.

Lê as credenciais via config (mesmo secrets.toml da app). Sem dependências extra.
"""
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from config import SUPABASE_URL, SUPABASE_KEY

LOG = Path(__file__).parent / "keepalive.log"


def _log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        _log("ERRO: SUPABASE_URL/KEY em falta.")
        return 1
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/clients?select=id&limit=1"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            _log(f"OK {r.status} — keep-alive {SUPABASE_URL}")
        return 0
    except urllib.error.HTTPError as e:
        # Mesmo um 4xx conta como atividade (o pedido chegou à BD)
        _log(f"resposta {e.code} — keep-alive na mesma (pedido chegou ao projeto)")
        return 0
    except Exception as e:
        _log(f"ERRO keep-alive: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
