"""
Auth Manager — Autenticação Multi-Utilizador
=============================================
Login por email/password com PBKDF2-SHA256.
Perfis: owner | comercial_interno | contractor | administrativa
"""

import hashlib
import os
import binascii
from datetime import datetime
from config import SUPABASE_URL, SUPABASE_KEY

# ── Perfis e permissões ────────────────────────────────────────────────────────

ROLES = ["owner", "comercial_interno", "contractor", "administrativa"]

ROLE_LABELS = {
    "owner":             "Owner / Diretor",
    "comercial_interno": "Comercial Interno",
    "contractor":        "Comercial Contractor",
    "administrativa":    "Administrativa",
}

ROLE_BADGE_COLOR = {
    "owner":             "#CC0000",
    "comercial_interno": "#1F4E79",
    "contractor":        "#2E7D32",
    "administrativa":    "#6A1B9A",
}

# Páginas disponíveis por perfil
# Chaves têm de corresponder ao texto exato dos botões de nav em app.py
PAGES_BY_ROLE = {
    "owner": [
        "📊  Dashboard",
        "🆕  Nova Cotação",
        "📋  Deals em Curso",
        "👥  CRM — Clientes",
        "🤝  Fornecedores",
        "🏭  Pedido Fornecedor",
        "🔍  Pesquisar Produto",
        "🚚  Logística",
        "⚙️  Administração",
    ],
    "comercial_interno": [
        "📊  Dashboard",
        "🆕  Nova Cotação",
        "📋  Deals em Curso",
        "👥  CRM — Clientes",
        "🤝  Fornecedores",
        "🏭  Pedido Fornecedor",
        "🔍  Pesquisar Produto",
        "🚚  Logística",
    ],
    "contractor": [
        "🆕  Nova Cotação",
        "📋  Deals em Curso",
        "👥  CRM — Clientes",
        "🤝  Fornecedores",
        "🔍  Pesquisar Produto",
        "🚚  Logística",
    ],
    "administrativa": [
        "📋  Deals em Curso",
        "👥  CRM — Clientes",
        "🤝  Fornecedores",
        "🔍  Pesquisar Produto",
        "🚚  Logística",
    ],
}

# Acesso a margens reais (FC Final, UFC, EIS)
CAN_SEE_MARGINS = {"owner", "comercial_interno"}

# Pode criar/editar deals
CAN_EDIT_DEALS = {"owner", "comercial_interno", "contractor"}

# Vê apenas os seus próprios dados
OWN_DATA_ONLY = {"contractor"}


# ── Hash / Verify password ────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """PBKDF2-SHA256 com salt de 16 bytes. Devolve 'hex_salt:hex_dk'."""
    salt = os.urandom(16)
    dk   = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return binascii.hexlify(salt).decode() + ":" + binascii.hexlify(dk).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, dk_hex = stored_hash.split(":")
        salt = binascii.unhexlify(salt_hex)
        dk   = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
        return binascii.hexlify(dk).decode() == dk_hex
    except Exception:
        return False


# ── Supabase client ────────────────────────────────────────────────────────────

def _db():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Auth ───────────────────────────────────────────────────────────────────────

def login(email: str, password: str) -> dict | None:
    """
    Autentica utilizador. Devolve dict com dados do utilizador ou None.
    """
    try:
        res = _db().table("users").select("*").ilike("email", email.strip()).limit(1).execute()
        if not res.data:
            return None
        user = res.data[0]
        if not user.get("is_active", True):
            return None
        if not verify_password(password, user.get("password_hash", "")):
            return None
        # Atualizar last_login
        _db().table("users").update({
            "last_login": datetime.now().strftime("%Y-%m-%d %H:%M")
        }).eq("id", user["id"]).execute()
        return user
    except Exception as e:
        print(f"[auth] login erro: {e}")
        return None


def has_users() -> bool:
    """Verifica se há pelo menos um utilizador na base de dados."""
    try:
        res = _db().table("users").select("id", count="exact").limit(1).execute()
        return (res.count or 0) > 0
    except Exception:
        return False


# ── CRUD utilizadores ──────────────────────────────────────────────────────────

def add_user(name: str, email: str, password: str, role: str) -> tuple[bool, str]:
    """Cria utilizador. Devolve (True, id) ou (False, mensagem_erro)."""
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        res = _db().table("users").insert({
            "name":          name,
            "email":         email.strip().lower(),
            "password_hash": hash_password(password),
            "role":          role,
            "is_active":     True,
            "created_at":    now,
            "last_login":    None,
        }).execute()
        return True, str(res.data[0]["id"])
    except Exception as e:
        return False, str(e)


def list_users() -> list:
    try:
        res = _db().table("users").select(
            "id,name,email,role,is_active,created_at,last_login"
        ).order("name").execute()
        return res.data or []
    except Exception as e:
        print(f"[auth] list_users erro: {e}")
        return []


def update_user(user_id: str, data: dict) -> bool:
    try:
        _db().table("users").update(data).eq("id", user_id).execute()
        return True
    except Exception as e:
        print(f"[auth] update_user erro: {e}")
        return False


def reset_password(user_id: str, new_password: str) -> bool:
    try:
        _db().table("users").update({
            "password_hash": hash_password(new_password)
        }).eq("id", user_id).execute()
        return True
    except Exception as e:
        print(f"[auth] reset_password erro: {e}")
        return False
