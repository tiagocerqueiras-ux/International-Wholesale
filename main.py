#!/usr/bin/env python
"""
Cotação Agent — CLI de gestão de deals e cotações
BoxMovers Export | Worten

Uso:
  py main.py              — Menu interativo
  py main.py new          — Criar novo deal
  py main.py update       — Atualizar status de deal
  py main.py list         — Listar todos os deals
  py main.py followup     — Gerar email de follow-up
  py main.py search       — Pesquisar produto no simulador por nome
  py main.py cache        — Reconstruir cache do simulador
"""

import argparse
import sys
from pathlib import Path

# Garantir que o módulo pode ser importado de qualquer diretório
sys.path.insert(0, str(Path(__file__).parent))

from config import DEALS_FILE, STATUSES, SIMULATOR_FILE
from sku_lookup import lookup_skus, build_cache, search_by_name
from deal_tracker import (
    add_deal, update_status, update_margin,
    list_deals, get_deal, print_deals_table
)
from email_generator import generate_proposal, generate_followup, save_email_html


# ── Utilitários de input ──────────────────────────────────────────────────────

def ask(prompt: str, default: str = None) -> str:
    """Pede input ao utilizador com valor por defeito opcional."""
    if default is not None:
        val = input(f"  {prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"  {prompt}: ").strip()


def ask_int(prompt: str, default: int = 1) -> int:
    while True:
        raw = input(f"  {prompt} [{default}]: ").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print("  Por favor insere um número inteiro.")


def ask_float(prompt: str, default: float = 5.0) -> float:
    while True:
        raw = input(f"  {prompt} [{default}]: ").strip()
        if not raw:
            return default
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            print("  Por favor insere um número (ex: 5 ou 7.5).")


def select(prompt: str, options: list, default_idx: int = 0) -> str:
    """Menu numerado de seleção."""
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        marker = " ← padrão" if i - 1 == default_idx else ""
        print(f"    {i}. {opt}{marker}")
    while True:
        raw = input(f"  Escolha (1-{len(options)}): ").strip()
        if not raw:
            return options[default_idx]
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print("  Opção inválida.")


def divider(title: str = ""):
    line = "═" * 62
    print(f"\n  {line}")
    if title:
        print(f"  {title}")
        print(f"  {line}")


# ── Comando: novo deal ────────────────────────────────────────────────────────

def cmd_new():
    divider("NOVO DEAL — Cotação de Produtos")

    # Dados do cliente
    client   = ask("Nome do cliente")
    country  = ask("País destino")
    email    = ask("Email do cliente")
    language = select("Língua do email:", ["EN", "PT", "ES", "FR"], default_idx=0)
    notes    = ask("Notas (opcional)", default="")

    # Input dos SKUs
    print("\n  ── Produtos ──────────────────────────────────────────────")
    print("  Insere os SKUs a cotar.")
    print("  Formatos aceites:")
    print("    • Por vírgula:        2062910, 2062944, 2082709")
    print("    • Com quantidades:    2062910:100, 2062944:50")
    print("    • Misturado:          2062910:100, 2062944 (pede qty depois)")
    print()

    raw = ask("SKUs").strip()
    if not raw:
        print("  Nenhum SKU inserido. Operação cancelada.")
        return

    # Parsear SKUs e quantidades
    sku_qtys = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            sku, qty_str = part.split(":", 1)
            try:
                sku_qtys[sku.strip()] = int(qty_str.strip())
            except ValueError:
                sku_qtys[sku.strip()] = 1
        else:
            sku_qtys[part] = None  # quantidade pedida depois

    sku_list = list(sku_qtys.keys())

    # Lookup no simulador
    sim_ok = Path(SIMULATOR_FILE).exists()
    if not sim_ok:
        print(f"\n  ⚠  Simulador não encontrado em: {SIMULATOR_FILE}")
        print("  Coloca o ficheiro Simulador_AfricanMarkets.xlsx em Docs/")
        cont = ask("Continuar sem dados de pricing? (s/n)", "n").lower()
        if cont != "s":
            return
        lookup_result = {s: None for s in sku_list}
    else:
        print(f"\n  A consultar {len(sku_list)} SKU(s)...")
        lookup_result = lookup_skus(sku_list)

    found     = [k for k, v in lookup_result.items() if v]
    not_found = [k for k, v in lookup_result.items() if not v]

    if not_found:
        print(f"\n  ⚠  Não encontrados no simulador: {', '.join(not_found)}")
        if not found:
            cont = ask("Nenhum SKU encontrado. Continuar mesmo assim? (s/n)", "n").lower()
            if cont != "s":
                return

    # Mostrar resumo e pedir quantidades em falta
    print("\n  ── Resumo dos produtos ───────────────────────────────────")

    skus_data = {}
    for sku in sku_list:
        data = lookup_result.get(sku)
        qty  = sku_qtys[sku]
        if qty is None:
            qty = ask_int(f"Quantidade para SKU {sku}", default=1)

        skus_data[sku] = {"qty": qty, "data": data or {}}

        if data:
            uc       = data.get("unit_cost")
            eis_da   = data.get("eis_da", 0)
            sell_in  = data.get("sell_in")
            sell_out = data.get("sell_out")
            stock    = data.get("stock")

            uc_str  = f"{uc:.4f} €" if uc is not None else "N/D"
            eis_str = f"{eis_da:.4f} €" if eis_da and eis_da > 0 else "—"
            si_str  = f"{sell_in:.4f} €"  if sell_in  else "—"
            so_str  = f"{sell_out:.4f} €" if sell_out else "—"

            print(f"\n  ✓ {sku} — {data.get('name','')[:55]}")
            print(f"    Marca: {data.get('brand','-')} | Stock: {int(stock) if stock else 'N/D'} un.")
            print(f"    Unit Final Cost : {uc_str}")
            print(f"    EIS Dir. Autor  : {eis_str}")
            print(f"    Apoio Sell-In   : {si_str}")
            print(f"    Apoio Sell-Out  : {so_str}")
            print(f"    Quantidade      : {qty} un.")
        else:
            print(f"\n  ✗ {sku} — NÃO ENCONTRADO (qty: {qty})")

    # Margem
    print()
    margin_pct = ask_float("Margem pretendida % sobre Unit Final Cost", default=5.0)

    # Calcular totais para preview
    total_cost = sum(
        (info["data"].get("unit_cost") or 0) * info["qty"]
        for info in skus_data.values()
    )
    total_pvp = sum(
        (info["data"].get("unit_cost") or 0) * (1 + margin_pct / 100) * info["qty"]
        for info in skus_data.values()
    )
    print(f"\n  Total custo     : {total_cost:.2f} €")
    print(f"  Total proposta  : {total_pvp:.2f} €  (margem {margin_pct:.1f}%)")

    # Confirmar
    print()
    conf = ask("Confirmar e criar deal? (s/n)", "s").lower()
    if conf != "s":
        print("  Cancelado.")
        return

    # Criar deal
    deal_id = add_deal(
        client=client,
        country=country,
        email=email,
        language=language,
        skus_data=skus_data,
        notes=notes,
        margin_pct=round(margin_pct, 2),
        pvp_total=round(total_pvp, 2),
    )
    print(f"\n  ✅ Deal criado: {deal_id}")

    # Gerar email de proposta?
    gen = ask("\n  Gerar email de proposta agora? (s/n)", "s").lower()
    if gen == "s":
        print("  A gerar email com Claude AI...")
        try:
            html_body, pvp_total, margin_calc = generate_proposal(
                client_name=client,
                client_email=email,
                country=country,
                language=language,
                skus_data=skus_data,
                deal_id=deal_id,
                margin=margin_pct / 100,
                notes=notes,
            )
            save_email_html(deal_id, html_body, "proposal")
            update_margin(deal_id, margin_calc, pvp_total)
            update_status(deal_id, "Enviado", "Email de proposta gerado")
            print(f"  ✅ Email aberto no browser para revisão e envio")
        except Exception as e:
            print(f"  ⚠  Erro ao gerar email: {e}")

    print(f"\n  Ficheiro de tracking: {DEALS_FILE}")


# ── Comando: atualizar status ─────────────────────────────────────────────────

def cmd_update():
    divider("ATUALIZAR DEAL")

    deals = list_deals()
    if not deals:
        print("  Sem deals registados.")
        return

    print_deals_table(deals[-25:])  # últimos 25

    deal_id    = ask("\n  Deal ID a atualizar (ex: BM-2026-001)")
    new_status = select("Novo status:", STATUSES)
    notes      = ask("Notas (opcional)", default="")

    ok = update_status(deal_id, new_status, notes)
    if not ok:
        return

    print(f"  ✅ {deal_id} → {new_status}")

    # Se Follow-up: oferecer geração de email
    if new_status == "Follow-up":
        gen = ask("  Gerar email de follow-up? (s/n)", "s").lower()
        if gen == "s":
            deal = get_deal(deal_id)
            if deal:
                days = ask_int("  Dias desde o envio original", default=7)
                lang = str(deal.get("Língua", "EN"))
                print("  A gerar follow-up...")
                try:
                    html = generate_followup(deal, lang, days, notes)
                    save_email_html(deal_id, html, "followup")
                    print("  ✅ Follow-up aberto no browser")
                except Exception as e:
                    print(f"  ⚠  Erro: {e}")


# ── Comando: listar deals ─────────────────────────────────────────────────────

def cmd_list():
    divider("LISTA DE DEALS")

    filter_options = ["Todos"] + STATUSES
    choice = select("Filtrar por status:", filter_options, default_idx=0)
    status_filter = None if choice == "Todos" else choice

    deals = list_deals(status_filter)
    label = f" com status '{status_filter}'" if status_filter else ""
    print(f"\n  {len(deals)} deal(s){label}")

    if deals:
        verbose = ask("  Mostrar detalhes? (s/n)", "n").lower() == "s"
        print_deals_table(deals, verbose=verbose)

    print(f"\n  Ficheiro de tracking: {DEALS_FILE}")


# ── Comando: follow-up ────────────────────────────────────────────────────────

def cmd_followup():
    divider("FOLLOW-UP DE PROPOSTA")

    deals = list_deals()
    if not deals:
        print("  Sem deals registados.")
        return

    # Mostrar apenas deals que fazem sentido para follow-up
    pending = [d for d in deals if d.get("Status") in ("Enviado", "Em Negociação", "Follow-up")]
    if pending:
        print("  Deals pendentes:")
        print_deals_table(pending)
    else:
        print_deals_table(deals[-15:])

    deal_id = ask("\n  Deal ID para follow-up")
    deal = get_deal(deal_id)
    if not deal:
        print(f"  Deal '{deal_id}' não encontrado.")
        return

    print(f"\n  Cliente : {deal.get('Cliente')} ({deal.get('País')})")
    print(f"  Status  : {deal.get('Status')}")
    print(f"  Produtos: {str(deal.get('Produtos',''))[:80]}...")

    days  = ask_int("  Dias desde envio original", default=7)
    notes = ask("  Notas adicionais (opcional)", default="")
    lang  = str(deal.get("Língua", "EN"))

    print("  A gerar follow-up com Claude AI...")
    try:
        html = generate_followup(deal, lang, days, notes)
        save_email_html(deal_id, html, "followup")
        update_status(deal_id, "Follow-up", notes or f"Follow-up enviado ({days}d)")
        print("  ✅ Follow-up aberto no browser")
    except Exception as e:
        print(f"  ⚠  Erro: {e}")


# ── Comando: pesquisa por nome ────────────────────────────────────────────────

def cmd_search():
    divider("PESQUISAR PRODUTO NO SIMULADOR")

    if not Path(SIMULATOR_FILE).exists():
        print(f"  ⚠  Simulador não encontrado: {SIMULATOR_FILE}")
        return

    query = ask("  Pesquisar por nome/marca (ex: Philips Airfryer)")
    print(f"  A pesquisar '{query}'...")

    results = search_by_name(query, max_results=15)
    if not results:
        print("  Sem resultados.")
        return

    print(f"\n  {len(results)} resultado(s):\n")
    print(f"  {'SKU':<10} {'Marca':<15} {'Produto':<55} {'Unit Cost':>10} {'Stock':>8}")
    print(f"  {'─'*100}")
    for r in results:
        uc = r.get("unit_cost")
        st = r.get("stock")
        print(
            f"  {r['sku_id']:<10} "
            f"{r.get('brand',''):<15} "
            f"{r.get('name','')[:54]:<55} "
            f"{f'{uc:.2f} €':>10} "
            f"{f'{int(st)} un':>8}" if uc and st else
            f"  {r['sku_id']:<10} {r.get('brand',''):<15} {r.get('name','')[:54]:<55} {'N/D':>10} {'N/D':>8}"
        )


# ── Comando: reconstruir cache ────────────────────────────────────────────────

def cmd_cache():
    divider("RECONSTRUIR CACHE DO SIMULADOR")

    path = Path(SIMULATOR_FILE)
    if not path.exists():
        print(f"  Simulador não encontrado: {SIMULATOR_FILE}")
        custom = ask("  Caminho alternativo (ou Enter para cancelar)", default="")
        if not custom:
            return
        build_cache(custom, force=True)
    else:
        build_cache(force=True)

    print("  ✅ Cache reconstruído.")


# ── Menu principal ────────────────────────────────────────────────────────────

COMMANDS = {
    "new":      (cmd_new,      "Criar novo deal / cotação"),
    "update":   (cmd_update,   "Atualizar status de deal"),
    "list":     (cmd_list,     "Listar deals"),
    "followup": (cmd_followup, "Gerar email de follow-up"),
    "search":   (cmd_search,   "Pesquisar produto no simulador"),
    "cache":    (cmd_cache,    "Reconstruir cache do simulador"),
}


def interactive_menu():
    """Menu interativo quando não é passado nenhum argumento."""
    print()
    print("  Escolhe uma opção:\n")
    keys = list(COMMANDS.keys())
    for i, key in enumerate(keys, 1):
        _, desc = COMMANDS[key]
        print(f"    {i}. {desc}")
    print()

    raw = input("  Opção (1-6 ou nome): ").strip()

    # Tentar por número
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(keys):
            COMMANDS[keys[idx]][0]()
            return
    except ValueError:
        pass

    # Tentar por nome
    if raw in COMMANDS:
        COMMANDS[raw][0]()
    else:
        print("  Opção inválida.")


def main():
    parser = argparse.ArgumentParser(
        description="Cotação Agent — BoxMovers Export | Worten",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:<10} — {v[1]}" for k, v in COMMANDS.items()),
    )
    subparsers = parser.add_subparsers(dest="command")
    for key in COMMANDS:
        subparsers.add_parser(key, help=COMMANDS[key][1])

    args = parser.parse_args()

    print("=" * 62)
    print("  Cotação Agent — BoxMovers Export | Worten")
    print("=" * 62)

    if args.command and args.command in COMMANDS:
        COMMANDS[args.command][0]()
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
