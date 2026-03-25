"""
SKU Lookup — Consulta SKUs
==========================
Estratégia de carregamento (por ordem de prioridade):
  1. Memória (module-level cache) — subsegundo após primeira carga
  2. Cache JSON local (.cache/simulator_index.json) — modo local/dev
  3. Supabase Storage (bucket "sku-cache") — modo cloud

Para actualizar o índice na cloud:
  python upload_sku_cache.py
"""

import json
import time
from pathlib import Path

from config import (
    SIMULATOR_FILE, CACHE_DIR, SIMULATOR_CACHE,
    ENTITY_FILTER, ENTITY_PRIORITY, SIMULATOR_HEADER_ROW, SIMULATOR_COLS,
    SUPABASE_URL, SUPABASE_KEY,
)

# ── Cache em memória (partilhado por todos os utilizadores na mesma sessão) ────
_INDEX: dict = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _float_or_none(val):
    try:
        import math
        f = float(val) if val is not None else None
        return None if (f is None or math.isnan(f)) else f
    except (TypeError, ValueError):
        return None


def _str_val(val):
    return str(val).strip() if val is not None else ""


def _cell(row, col_idx):
    try:
        cell = row[col_idx - 1]
        return cell.value if hasattr(cell, "value") else cell
    except (IndexError, AttributeError):
        return None


def _get_ufc_raw(unit_cost, pcl) -> dict:
    ufc_raw = unit_cost if unit_cost is not None else pcl
    source  = "UFC" if unit_cost is not None else ("PCL" if pcl is not None else None)
    return {"ufc_raw": ufc_raw, "cost_source": source}


# ── Supabase Storage ──────────────────────────────────────────────────────────

def _download_from_supabase() -> dict:
    """Descarrega o índice JSON (gzip) do Supabase Storage bucket 'sku-cache'."""
    import gzip
    import urllib.request

    url = f"{SUPABASE_URL}/storage/v1/object/sku-cache/simulator_index.json.gz"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    return json.loads(gzip.decompress(data).decode("utf-8"))


def upload_to_supabase(index: dict):
    """Envia o índice JSON para o Supabase Storage (chamado pelo script de migração)."""
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    data   = json.dumps(index, ensure_ascii=False).encode("utf-8")
    client.storage.from_("sku-cache").upload(
        "simulator_index.json", data,
        {"content-type": "application/json", "upsert": "true"}
    )
    print(f"  Upload concluído: {len(index):,} SKUs → Supabase Storage")


# ── Cache local ───────────────────────────────────────────────────────────────

def _cache_is_valid(simulator_path: Path) -> bool:
    if not SIMULATOR_CACHE.exists():
        return False
    if not simulator_path.exists():
        return False
    return SIMULATOR_CACHE.stat().st_mtime >= simulator_path.stat().st_mtime


def _load_local_cache() -> dict:
    with open(SIMULATOR_CACHE, encoding="utf-8") as f:
        return json.load(f)


def _save_local_cache(index: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SIMULATOR_CACHE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)


# ── Indexação local (para rebuild) ───────────────────────────────────────────

def _make_local_copy(source: Path) -> Path:
    import shutil
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local_copy = CACHE_DIR / "Simulador_AfricanMarkets_local.xlsx"
    try:
        shutil.copy2(str(source), str(local_copy))
        return local_copy
    except PermissionError:
        if local_copy.exists():
            return local_copy
        raise RuntimeError(
            "Ficheiro do simulador está bloqueado. Fecha o Excel e tenta de novo."
        )


def _build_index_pandas(path: Path, entity_filter) -> dict:
    import pandas as pd

    COLS = SIMULATOR_COLS
    cols_0based    = {name: idx - 1 for name, idx in COLS.items()}
    usecols_indices = sorted(set(cols_0based.values()))

    df = pd.read_excel(
        str(path),
        header=SIMULATOR_HEADER_ROW - 1,
        usecols=usecols_indices,
        dtype=str,
        engine="openpyxl",
    )

    sorted_indices = sorted(usecols_indices)
    rename_map = {}
    for field, idx_0 in cols_0based.items():
        if idx_0 in sorted_indices:
            pos = sorted_indices.index(idx_0)
            if pos < len(df.columns):
                rename_map[df.columns[pos]] = field
    df = df.rename(columns=rename_map)

    if "status" in df.columns:
        df = df[df["status"].astype(str).str.strip() == "A"]

    allowed = entity_filter if isinstance(entity_filter, (set, list)) else {entity_filter}
    if allowed and "entity" in df.columns:
        df = df[df["entity"].astype(str).str.strip().isin(allowed)]
        priority_map = {e: i for i, e in enumerate(ENTITY_PRIORITY)}
        df = df.copy()
        df["_prio"] = df["entity"].astype(str).str.strip().map(lambda x: priority_map.get(x, 99))
        df = df.sort_values("_prio")
        if "sku_id" in df.columns:
            df = df.drop_duplicates(subset=["sku_id"], keep="first")
        df = df.drop(columns=["_prio"])

    index = {}
    for _, row in df.iterrows():
        key = str(row.get("sku_id", "") or "").strip()
        if not key or key == "nan":
            continue
        # Normalizar: "5879983.0" → "5879983"
        if key.endswith(".0"):
            key = key[:-2]
        index[key] = {
            "sku_id":    key,
            "entity":    str(row.get("entity", "") or ""),
            "ean":       str(row.get("ean", "") or ""),
            "name":      str(row.get("name", "") or ""),
            "cat":       str(row.get("cat", "") or ""),
            "subcat":    str(row.get("subcat", "") or ""),
            "brand":     str(row.get("brand", "") or ""),
            "pvp_pt":    _float_or_none(row.get("pvp_pt")),
            "stock":     _float_or_none(row.get("stock")),
            "pcl":       _float_or_none(row.get("pcl")),
            "eis_total": _float_or_none(row.get("eis_total")),
            "eis_da":    _float_or_none(row.get("eis_da")) or 0.0,
            "eis_reee":  _float_or_none(row.get("eis_reee")),
            "cgf_reb":   _float_or_none(row.get("cgf_reb")),
            "cgf_com":   _float_or_none(row.get("cgf_com")),
            "sell_in":   _float_or_none(row.get("sell_in")),
            "sell_out":  _float_or_none(row.get("sell_out")),
            **_get_ufc_raw(
                _float_or_none(row.get("unit_cost")),
                _float_or_none(row.get("pcl")),
            ),
        }

    return index


# ── API Pública ───────────────────────────────────────────────────────────────

def build_cache(simulator_path=None, entity=None, force=False) -> dict:
    """
    Carrega o índice de SKUs por ordem de prioridade:
      1. Memória (_INDEX)
      2. simulator_index.json.gz bundled no repositório (cloud/GitHub)
      3. Cache JSON local
      4. Supabase Storage
    """
    global _INDEX
    if _INDEX and not force:
        return _INDEX

    # 0. Ficheiro gz bundled no repositório (Streamlit Cloud)
    import gzip
    bundled_gz = Path(__file__).parent / "simulator_index.json.gz"
    if bundled_gz.exists() and not force:
        try:
            with open(bundled_gz, "rb") as f:
                _INDEX = json.loads(gzip.decompress(f.read()).decode("utf-8"))
            print(f"  Cache bundled carregado: {len(_INDEX):,} SKUs")
            return _INDEX
        except Exception as e:
            print(f"  ⚠  Erro ao ler bundled gz: {e}")

    # 1. Cache local (modo dev / Windows)
    source_path = Path(simulator_path or SIMULATOR_FILE)
    if not force and _cache_is_valid(source_path):
        print("  Cache local válido, a carregar...", end="\r")
        _INDEX = _load_local_cache()
        print(f"  Cache carregado: {len(_INDEX):,} SKUs          ")
        return _INDEX

    if SIMULATOR_CACHE.exists() and not force:
        print("  Cache local encontrado, a carregar...", end="\r")
        _INDEX = _load_local_cache()
        print(f"  Cache carregado: {len(_INDEX):,} SKUs          ")
        return _INDEX

    # 2. Supabase Storage (modo cloud)
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            print("  A descarregar índice do Supabase Storage...")
            _INDEX = _download_from_supabase()
            print(f"  Índice carregado da cloud: {len(_INDEX):,} SKUs")
            return _INDEX
        except Exception as e:
            print(f"  ⚠  Supabase Storage indisponível: {e}")

    # 3. Rebuild local a partir do Excel
    if source_path.exists():
        print(f"  A indexar {source_path.name}...")
        entity_filter = entity or ENTITY_FILTER
        path = _make_local_copy(source_path)
        try:
            import pandas
            _INDEX = _build_index_pandas(path, entity_filter)
        except ImportError:
            _INDEX = {}
        _save_local_cache(_INDEX)
        return _INDEX

    print("  ⚠  Nenhuma fonte de dados disponível para o índice de SKUs.")
    return {}


def lookup_skus(sku_list: list, simulator_path=None) -> dict:
    if not sku_list:
        return {}
    index = build_cache(simulator_path)
    return {str(sku).strip(): index.get(str(sku).strip()) for sku in sku_list}


def search_by_name(query: str, max_results: int = 20) -> list:
    index = build_cache()
    q = query.lower()
    return [
        v for v in index.values()
        if q in v.get("name", "").lower() or q in v.get("brand", "").lower()
    ][:max_results]


def search_by_ean(ean: str) -> dict | None:
    index = build_cache()
    ean_clean = str(ean).strip()
    return next((v for v in index.values() if v.get("ean", "").strip() == ean_clean), None)


def lookup_by_eans(ean_list: list) -> dict:
    if not ean_list:
        return {}
    index = build_cache()
    ean_index = {v.get("ean", "").strip(): v for v in index.values() if v.get("ean")}
    return {str(e).strip(): ean_index.get(str(e).strip()) for e in ean_list}
