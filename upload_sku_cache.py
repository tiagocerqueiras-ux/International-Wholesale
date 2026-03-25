"""
upload_sku_cache.py — Gera o índice de SKUs e guarda localmente para commit no GitHub
======================================================================================
1. Lê o Simulador_AfricanMarkets.xlsx (via atalho local)
2. Constrói o índice JSON
3. Guarda como simulator_index.json.gz na pasta cotacao_agent/
   → Faz commit deste ficheiro para o GitHub → Streamlit Cloud lê-o directamente

Uso:
  python upload_sku_cache.py
  python upload_sku_cache.py --force   # Força rebuild mesmo com cache válido
"""

import sys
import os
import json
import gzip
from pathlib import Path


def main():
    force = "--force" in sys.argv

    print("=" * 55)
    print("  International Wholesale — Gerar SKU Cache")
    print("=" * 55)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sku_lookup import build_cache

    # Passo 1: Construir índice local
    print("\n[1/2] A construir índice de SKUs...")
    index = build_cache(force=force)

    if not index:
        print("  ❌  Índice vazio. Verifica o ficheiro simulador.")
        sys.exit(1)

    print(f"  ✅  {len(index):,} SKUs indexados.")

    # Passo 2: Guardar como .gz na pasta do projecto
    print("\n[2/2] A guardar ficheiro comprimido...")
    out_path = Path(__file__).parent / "simulator_index.json.gz"
    raw  = json.dumps(index, ensure_ascii=False).encode("utf-8")
    data = gzip.compress(raw, compresslevel=6)

    with open(out_path, "wb") as f:
        f.write(data)

    print(f"  ✅  Ficheiro guardado: {out_path.name}")
    print(f"      Tamanho: {len(raw)/1024/1024:.1f} MB → comprimido: {len(data)/1024/1024:.1f} MB")

    print("\n" + "=" * 55)
    print("  Próximos passos:")
    print("  1. git add simulator_index.json.gz")
    print("  2. git commit -m 'add sku cache'")
    print("  3. git push")
    print("  4. Deploy no Streamlit Community Cloud")
    print("=" * 55)


if __name__ == "__main__":
    main()
