"""
controlo_sync.py — Sincroniza deals confirmados (BD) → Controlo_Deals_2026.xlsx
===============================================================================
O auto-registo em update_status só escreve quando a app corre NESTA máquina;
deals confirmados na app cloud (Railway) ficam por registar. Este script (tarefa
diária) procura deals em estado qualificável que ainda não estão no ficheiro de
controlo e acrescenta-os. Idempotente (dedup pelo registry do controlo_writer).

Uso:  py controlo_sync.py
"""
import sys
import json
import datetime
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import controlo_writer as cw
from config import SUPABASE_URL, SUPABASE_KEY

STATES = ["Encomenda Confirmada", "Em Preparação", "Expedido", "Entregue", "Faturado"]
LOG = HERE / "controlo_sync.log"


def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main() -> int:
    if not Path(cw.CONTROLO_FILE).exists():
        log(f"Ficheiro de controlo não encontrado: {cw.CONTROLO_FILE}")
        return 2
    H = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    q = urllib.parse.quote('("' + '","'.join(STATES) + '")')
    u = (f"{SUPABASE_URL.rstrip('/')}/rest/v1/deals"
         f"?select=deal_id,client,company,status,business,created_at,skus_detail"
         f"&status=in.{q}&order=created_at")
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=60) as r:
            rows = json.loads(r.read())
    except Exception as e:
        log(f"ERRO a consultar a BD: {e}")
        return 3

    reg = cw._load_reg()
    missing = [d for d in rows if d.get("deal_id") not in reg]
    if not missing:
        log(f"Nada a sincronizar ({len(rows)} deals qualificáveis, todos registados).")
        return 0

    total = 0
    for d in missing:
        try:
            n, msg = cw.append_deal(
                {"deal_id": d["deal_id"], "client": d.get("client"),
                 "company": d.get("company"), "status": d.get("status"),
                 "created_at": d.get("created_at"),
                 "skus_detail": d.get("skus_detail") or {}},
                business=d.get("business") or "",
                status_label=cw.status_to_label(d.get("status")))
            total += n
            log(f"{d['deal_id']}: {msg}")
        except PermissionError:
            log(f"{d['deal_id']}: ficheiro bloqueado (aberto no Excel) — fica para a próxima execução.")
            return 4
        except Exception as e:
            log(f"{d['deal_id']}: ERRO {e}")
    log(f"Sincronização concluída: {len(missing)} deal(s), {total} linha(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
