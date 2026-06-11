"""
refresh_transport_cache.py — Atualização automática do Simulador de Exportação
==============================================================================
Vigia a pasta SharePoint (sincronizada via OneDrive):
   Gestão de Fretes › Simuladores › Simulador Transporte Terrestre › <ano> › Partilhado B2B
Deteta o master mais recente  Simulador_Exportacao_V{mês}.{ano} - B2B.xlsx
(ignora variantes por cliente), e se houver versão nova:
  1. Reconstrói data/transport_cache.json (via build_transport_cache da app)
  2. Só faz commit + push se os DADOS mudarem (evita redeploys inúteis)
  3. O push faz o Railway redeployar com as tarifas novas.

Uso:
  py refresh_transport_cache.py            # só atua se houver versão nova
  py refresh_transport_cache.py --force    # força rebuild + push
  py refresh_transport_cache.py --no-push  # rebuild local, sem git

Enquanto a pasta do SharePoint NÃO estiver sincronizada no OneDrive, o script
sai graciosamente a avisar (não falha).
"""
import sys, os, re, json, hashlib, subprocess, datetime, shutil, tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

STATE      = HERE / ".cache" / "last_transport.json"
LOGFILE    = HERE / "refresh_transport_cache.log"
CACHE_REL  = "data/transport_cache.json"

FORCE   = "--force" in sys.argv
NO_PUSH = "--no-push" in sys.argv

MASTER_RE = re.compile(r"^Simulador_Exportacao_V[\d.]+ - B2B\.xlsx$", re.IGNORECASE)
VER_RE    = re.compile(r"_V([\d.]+) - B2B\.xlsx$", re.IGNORECASE)

# Raízes onde a biblioteca pode aparecer (OneDrive shortcut ou Sync)
SYNC_ROOTS = [Path.home() / "OneDrive - Worten", Path.home() / "Worten"]
LEAF       = "partilhado b2b"
MUST       = "simulador transporte terrestre"


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


def save_state(d: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def version_key(name: str):
    m = VER_RE.search(name)
    if not m:
        return None
    parts = m.group(1).split(".")
    try:
        year  = int(parts[-1])
        month = int(parts[0])
        sub   = int(parts[1]) if len(parts) >= 3 else 0
        year4 = 2000 + year if year < 100 else year
        return (year4, month, sub)
    except Exception:
        return None


def find_library(state: dict):
    """Localiza a pasta '...Simulador Transporte Terrestre/<ano>/Partilhado B2B' sincronizada."""
    cached = state.get("folder")
    if cached and Path(cached).is_dir():
        return Path(cached)

    found = []
    for root in SYNC_ROOTS:
        if not root.exists():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, _ in os.walk(root, onerror=lambda e: None):
            # podar
            if len(Path(dirpath).parts) - base_depth > 12:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".")
                           and d.lower() not in ("__pycache__", "node_modules", "appdata")]
            low = dirpath.lower()
            if low.endswith(LEAF) and MUST in low:
                found.append(Path(dirpath))
    if not found:
        return None
    # se houver várias (vários anos), escolher a de ano mais alto no caminho
    def year_in_path(p: Path):
        yrs = [int(x) for x in p.parts if x.isdigit() and len(x) == 4]
        return max(yrs) if yrs else 0
    return max(found, key=year_in_path)


def git(*args):
    return subprocess.run(["git", *args], cwd=str(HERE), capture_output=True, text=True)


def main() -> int:
    state = load_state()

    folder = find_library(state)
    if not folder:
        log("Pasta do Simulador de Exportação NÃO encontrada localmente. "
            "Sincroniza no OneDrive: SharePoint 'Gestão de Fretes' › Simuladores › "
            "Simulador Transporte Terrestre › <ano> › Partilhado B2B (Opção A). Nada a fazer.")
        return 0
    state["folder"] = str(folder)
    log(f"Pasta: {folder}")

    masters = [p for p in folder.iterdir() if p.is_file() and MASTER_RE.match(p.name)]
    if not masters:
        log("Pasta encontrada mas sem masters 'Simulador_Exportacao_V*.* - B2B.xlsx'. Nada a fazer.")
        save_state(state)
        return 0

    newest = max(masters, key=lambda p: (version_key(p.name) or (0, 0, 0), p.stat().st_mtime))
    nk = version_key(newest.name)
    log(f"Master mais recente: {newest.name} (versão={nk}, "
        f"{datetime.datetime.fromtimestamp(newest.stat().st_mtime):%Y-%m-%d %H:%M})")

    last_ver = tuple(state["version"]) if state.get("version") else None
    if not FORCE and last_ver and nk and tuple(nk) <= last_ver:
        log(f"Sem versão nova (última processada: {state.get('file')}). Nada a fazer.")
        save_state(state)
        return 0

    log("Versão nova — a reconstruir transport_cache.json...")
    tmp = Path(tempfile.gettempdir()) / ("_tr_" + newest.name)
    shutil.copy2(newest, tmp)
    import transport_lookup as tl
    tl.TRANSPORT_FILE = tmp            # apontar o build ao novo ficheiro
    cache = tl.build_transport_cache()  # escreve data/transport_cache.json
    try:
        tmp.unlink()
    except Exception:
        pass

    n_dest   = len(cache.get("destinations") or {})
    new_hash = hashlib.sha256(json.dumps(cache, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    log(f"Cache reconstruída: {n_dest} destinos.")

    def commit_state():
        state.update({
            "file": newest.name, "version": list(nk) if nk else None,
            "mtime": newest.stat().st_mtime, "data_hash": new_hash,
            "destinations": n_dest,
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        save_state(state)

    if not FORCE and new_hash == state.get("data_hash"):
        log("Versão nova mas DADOS iguais — sem commit/push.")
        git("checkout", "--", CACHE_REL)   # descartar alteração byte-only
        commit_state()
        return 0

    commit_state()

    if NO_PUSH:
        log("--no-push: cache local atualizada (sem git).")
        return 0

    log("A publicar no GitHub (→ redeploy Railway)...")
    if git("add", CACHE_REL).returncode != 0:
        log("git add falhou."); return 4
    c = git("commit", "-m", f"Auto: atualiza transport_cache ({newest.name}) — {n_dest} destinos")
    if c.returncode != 0:
        out = (c.stdout + c.stderr).lower()
        if "nothing to commit" in out:
            log("Nada para commitar."); return 0
        log(f"git commit falhou: {c.stdout}{c.stderr}"); return 5
    p = git("push", "origin", "main")
    if p.returncode != 0:
        log(f"git push falhou: {p.stderr.strip()}"); return 6
    log("Publicado. O Railway vai redeployar automaticamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
