"""
build_bm_snapshot.py — gera data/bm_deals_snapshot.json
=======================================================
O dashboard executivo lê os deals reais do BoxMovers via boxmovers_reader.
Localmente lê os Excel do SISO; na cloud (Railway, sem Excel) lê este snapshot
JSON commitado. Este script regenera o snapshot a partir dos ficheiros SISO:

  - 2026: BoxMovers2026_i.xlsx
  - 2025: BoxMovers2025_actual.xlsx

Estados contados (= "concluded" no reader): CONCLUÍDO (fechado/faturado) + PO
(em tratamento / fase de entrega). CANCELADO é ignorado.

Uso:  py build_bm_snapshot.py [--deep-info]
  --deep-info : enriquece marca/categoria via folha "Deep Info 2.0" (~950k linhas,
                lento). Por omissão usa marca/cat da própria folha DEALS (rápido).
"""
import sys
import json
import warnings
from pathlib import Path

import boxmovers_reader as br

warnings.simplefilter("ignore")

_SISO = (Path.home() / "Worten"
         / "B2B Business Unit - PART.& INT. EXP. AND TRAD. - Documents"
         / "ÁREAS DE NEGÓCIO" / "BOX MOVERS - PT_ES"
         / "03.CONTROLO GESTÃO" / "13. SISO")

FILES = [
    (2026, _SISO / "BoxMovers2026_i.xlsx"),
    (2025, _SISO / "BoxMovers2025_actual.xlsx"),
]

OUT = Path(__file__).parent / "data" / "bm_deals_snapshot.json"
SNAP_FIELDS = ("client", "brand", "cat", "sku", "revenue", "mg_eur", "mg_pct",
               "year", "month", "status")


def main():
    use_deep = "--deep-info" in sys.argv

    # Apontar o reader para os ficheiros certos
    br._get_bm_paths = lambda: [(y, p) for y, p in FILES if p.exists()]
    if not use_deep:
        # Saltar a leitura da folha Deep Info (950k linhas) — marca/cat vêm de DEALS
        br._build_di_index = lambda wb, key: {}

    paths = br._get_bm_paths()
    if not paths:
        print("ERRO: nenhum ficheiro BoxMovers encontrado em", _SISO)
        sys.exit(1)
    for y, p in paths:
        print(f"  fonte {y}: {p.name}")

    rows = br.read_bm_deals(year_filter=None)
    snap = [{k: r.get(k) for k in SNAP_FIELDS} for r in rows]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")

    # Resumo
    import collections
    by_year = collections.Counter(r["year"] for r in rows)
    concl = [r for r in rows if r.get("concluded")]
    rev_by_year = collections.defaultdict(float)
    for r in concl:
        rev_by_year[r["year"]] += r.get("revenue") or 0.0
    print(f"\nEscrito: {OUT}  ({len(snap)} linhas)")
    print("Por ano (todas):", dict(by_year))
    print("Concluídos (CONCLUÍDO+PO):", len(concl))
    for y in sorted(rev_by_year):
        print(f"  receita {y}: {rev_by_year[y]:,.0f} EUR".replace(",", " "))


if __name__ == "__main__":
    main()
