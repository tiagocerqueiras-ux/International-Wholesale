"""
refresh_sku_cache.py — Atualização automática da cache de SKUs
==============================================================
Fluxo:
  1. Verifica se o Simulador_AfricanMarkets.xlsx (na rede) é mais recente
     do que a última versão já processada  -> gate barato por data.
  2. Se for, reconstrói o índice a partir do Excel e calcula um hash dos dados.
  3. Só faz commit + push de simulator_index.json.gz se os DADOS mudaram
     mesmo (não apenas a data do ficheiro) -> evita redeploys inúteis.
  4. O push faz o Railway redeployar com os dados novos.

Uso:
  py refresh_sku_cache.py            # só atua se houver versão nova
  py refresh_sku_cache.py --force    # força rebuild + commit + push
  py refresh_sku_cache.py --no-push  # reconstrói local, sem git
  py refresh_sku_cache.py --init     # semeia o estado sem reconstruir (setup)

Pensado para tarefa agendada do Windows (idempotente e silencioso quando
não há nada a fazer).
"""

import sys
import json
import gzip
import hashlib
import subprocess
import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from config import SIMULATOR_FILE, ENTITY_FILTER
from sku_lookup import _make_local_copy, _build_index_pandas, _save_local_cache

STATE   = HERE / ".cache" / "last_refresh.json"
GZ      = HERE / "simulator_index.json.gz"
LOGFILE = HERE / "refresh_sku_cache.log"

FORCE   = "--force" in sys.argv
NO_PUSH = "--no-push" in sys.argv
INIT    = "--init" in sys.argv


def log(msg: str):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(src_mtime: float, data_hash: str, skus: int, stk_mtime: float = 0.0):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "src_mtime":  src_mtime,
        "stk_mtime":  stk_mtime,
        "data_hash":  data_hash,
        "skus":       skus,
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def data_hash(index: dict) -> str:
    raw = json.dumps(index, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(HERE),
                          capture_output=True, text=True)


def main() -> int:
    src = Path(SIMULATOR_FILE)
    if not src.exists():
        log(f"ERRO: Simulador não encontrado em {src}. Abortado.")
        return 2

    src_mtime = src.stat().st_mtime
    state = load_state()

    # --init: semeia o estado a partir do gz atual, sem reconstruir
    if INIT:
        if not GZ.exists():
            log("--init: simulator_index.json.gz não existe. Corre sem --init primeiro.")
            return 1
        idx = json.loads(gzip.decompress(GZ.read_bytes()).decode("utf-8"))
        save_state(src_mtime, data_hash(idx), len(idx))
        log(f"Estado inicializado: {len(idx):,} SKUs | rede {datetime.datetime.fromtimestamp(src_mtime):%Y-%m-%d %H:%M}.")
        return 0

    # Gate 1 (barato): há versão nova na rede? (simulador OU stocks diários STK WHs)
    stk_mtime = 0.0
    try:
        import stock_whs as _swhs
        _stk_f = _swhs.find_file()
        stk_mtime = _stk_f.stat().st_mtime if _stk_f else 0.0
    except Exception:
        pass
    if not FORCE and src_mtime <= state.get("src_mtime", 0) \
            and stk_mtime <= state.get("stk_mtime", 0):
        log(f"Sem versão nova (simulador/stocks). Nada a fazer.")
        return 0

    log("Versão nova detetada (simulador ou stocks) — a reconstruir índice (1-3 min)...")
    local = _make_local_copy(src)
    index = _build_index_pandas(local, ENTITY_FILTER)
    if not index:
        log("ERRO: índice vazio — abortado sem escrever nada.")
        return 3
    log(f"{len(index):,} SKUs indexados.")

    new_hash = data_hash(index)
    _save_local_cache(index)

    # Gate 2: os dados mudaram mesmo?
    if new_hash == state.get("data_hash") and not FORCE:
        log("O ficheiro foi regravado mas os DADOS são iguais — sem commit/push.")
        save_state(src_mtime, new_hash, len(index), stk_mtime)
        return 0

    # Regenerar gz de produção
    payload = json.dumps(index, ensure_ascii=False).encode("utf-8")
    GZ.write_bytes(gzip.compress(payload, compresslevel=6))
    log(f"gz atualizado ({len(payload)/1024/1024:.1f} MB → {GZ.stat().st_size/1024/1024:.1f} MB).")
    save_state(src_mtime, new_hash, len(index), stk_mtime)

    if NO_PUSH:
        log("--no-push: rebuild local concluído (sem git).")
        return 0

    # Commit + push  ->  redeploy Railway
    log("A publicar no GitHub (→ redeploy Railway)...")
    if git("add", "simulator_index.json.gz").returncode != 0:
        log("git add falhou."); return 4
    when = datetime.datetime.fromtimestamp(src_mtime).strftime("%Y-%m-%d %H:%M")
    commit = git("commit", "-m", f"Auto: atualiza SKU cache (Simulador {when}) — {len(index)} SKUs")
    if commit.returncode != 0:
        out = (commit.stdout + commit.stderr).lower()
        if "nothing to commit" in out:
            log("Nada para commitar."); return 0
        log(f"git commit falhou: {commit.stdout}{commit.stderr}"); return 5
    push = git("push", "origin", "main")
    if push.returncode != 0:
        log(f"git push falhou: {push.stderr.strip()}"); return 6
    log("Publicado. O Railway vai redeployar automaticamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
