-- ============================================================================
-- PRODUÇÃO (pivot) — projeto Supabase dmgbiourejbdsqzlmjvs (conta acessível)
-- ----------------------------------------------------------------------------
-- A produção antiga (suhbpfygvmgijztsfkyu) ficou numa conta sem acesso.
-- Como os dados são descartáveis, recriamos o schema de PRODUÇÃO neste projeto,
-- já com os campos da Fase 1. Tabelas sem prefixo (clients/deals/suppliers/users)
-- — convivem com as test_* da sandbox no mesmo projeto.
--
-- Correr 1x no SQL Editor (Run). Idempotente (CREATE ... IF NOT EXISTS).
-- ============================================================================

-- ── CLIENTES (produção + campos Fase 1) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS clients (
  id                  BIGSERIAL PRIMARY KEY,
  company_name        TEXT,
  legal_name          TEXT,
  vat                 TEXT,
  country             TEXT,
  market              TEXT,
  region              TEXT,
  address             TEXT,
  zip_code            TEXT,
  city                TEXT,
  contact_name        TEXT,
  contact_role        TEXT,
  contact_email       TEXT,
  contact_phone       TEXT,
  contact_linkedin    TEXT,
  client_type         TEXT,
  status              TEXT DEFAULT 'Ativo',
  brands              JSONB DEFAULT '[]'::jsonb,
  categories          JSONB DEFAULT '[]'::jsonb,
  incoterm            TEXT,
  currency            TEXT DEFAULT 'EUR',
  payment_method      TEXT,
  payment_terms       TEXT,
  notes               TEXT,
  contacts            JSONB DEFAULT '[]'::jsonb,
  created_at          TEXT,
  updated_at          TEXT,
  -- Fase 1
  commercial_cert_doc TEXT,
  fin_contact_name    TEXT,
  fin_contact_email   TEXT,
  fin_contact_phone   TEXT,
  billing_email       TEXT,
  iban                TEXT,
  swift               TEXT,
  bank_proof_doc      TEXT,
  credit_insurance    TEXT,
  credit_limit        NUMERIC,
  ubos                JSONB DEFAULT '[]'::jsonb,
  delivery_addresses  JSONB DEFAULT '[]'::jsonb,
  documents           JSONB DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_clients_company ON clients(company_name);
CREATE INDEX IF NOT EXISTS idx_clients_vat     ON clients(vat);

-- ── DEALS (produção + Fase 1 client_id) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS deals (
  id                 BIGSERIAL PRIMARY KEY,
  deal_id            TEXT UNIQUE NOT NULL,
  created_at         TEXT,
  client             TEXT,
  country            TEXT,
  client_email       TEXT,
  language           TEXT,
  sku_ids            TEXT,
  products           TEXT,
  avg_unit_cost      NUMERIC,
  eis_da_total       NUMERIC,
  has_sell_in        TEXT,
  has_sell_out       TEXT,
  qty_total          INTEGER,
  proposed_value     NUMERIC,
  margin_pct         TEXT,
  incoterm           TEXT,
  payment_conditions TEXT,
  vat                TEXT,
  freight            NUMERIC,
  availability       TEXT,
  status             TEXT DEFAULT 'Rascunho',
  updated_at         TEXT,
  notes              TEXT,
  skus_detail        JSONB,
  salesperson_email  TEXT,
  company            TEXT,
  order_date         TEXT,
  expected_delivery  TEXT,
  actual_delivery    TEXT,
  invoice_number     TEXT,
  invoice_date       TEXT,
  invoice_value      NUMERIC,
  cmr_number         TEXT,
  packing_list       TEXT,
  supplier_ids       TEXT,
  client_id          BIGINT
);
CREATE INDEX IF NOT EXISTS idx_deals_status ON deals(status);
CREATE INDEX IF NOT EXISTS idx_deals_client ON deals(client);
CREATE INDEX IF NOT EXISTS idx_deals_dealid ON deals(deal_id);

-- ── FORNECEDORES ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS suppliers (
  id               BIGSERIAL PRIMARY KEY,
  supplier_name    TEXT,
  legal_name       TEXT,
  vat              TEXT,
  country          TEXT,
  brand            TEXT,
  brands           JSONB DEFAULT '[]'::jsonb,
  categories       JSONB DEFAULT '[]'::jsonb,
  contact_name     TEXT,
  contact_role     TEXT,
  contact_email    TEXT,
  contact_phone    TEXT,
  contact_linkedin TEXT,
  contacts         JSONB DEFAULT '[]'::jsonb,
  cgf              NUMERIC,
  payment_terms    TEXT,
  incoterm         TEXT,
  currency         TEXT,
  min_order        TEXT,
  lead_time        TEXT,
  supplier_type    TEXT,
  status           TEXT,
  notes            TEXT,
  created_at       TEXT,
  updated_at       TEXT
);

-- ── UTILIZADORES (login) ────────────────────────────────────────────────────
-- A app cria o 1.º owner sozinha no ecrã de login quando a tabela está vazia.
CREATE TABLE IF NOT EXISTS users (
  id            BIGSERIAL PRIMARY KEY,
  name          TEXT,
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role          TEXT DEFAULT 'comercial_interno',
  is_active     BOOLEAN DEFAULT TRUE,
  created_at    TEXT,
  last_login    TEXT
);
