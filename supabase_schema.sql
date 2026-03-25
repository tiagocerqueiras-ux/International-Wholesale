-- International Wholesale — Supabase Schema
-- Corre este script no SQL Editor do Supabase

-- ── Tabela principal de Deals ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS deals (
  id                BIGSERIAL PRIMARY KEY,
  deal_id           TEXT UNIQUE NOT NULL,
  created_at        TEXT,
  client            TEXT,
  country           TEXT,
  client_email      TEXT,
  language          TEXT,
  sku_ids           TEXT,
  products          TEXT,
  avg_unit_cost     NUMERIC,
  eis_da_total      NUMERIC,
  has_sell_in       TEXT,
  has_sell_out      TEXT,
  qty_total         INTEGER,
  proposed_value    NUMERIC,
  margin_pct        TEXT,
  incoterm          TEXT,
  payment_conditions TEXT,
  vat               TEXT,
  freight           NUMERIC,
  availability      TEXT,
  status            TEXT DEFAULT 'Rascunho',
  updated_at        TEXT,
  notes             TEXT,
  skus_detail       JSONB
);

-- Índice para pesquisa rápida por status e cliente
CREATE INDEX IF NOT EXISTS idx_deals_status    ON deals(status);
CREATE INDEX IF NOT EXISTS idx_deals_client    ON deals(client);
CREATE INDEX IF NOT EXISTS idx_deals_deal_id   ON deals(deal_id);

-- ── Bucket para cache do Simulador ─────────────────────────────────────────
-- Cria o bucket manualmente no painel Supabase:
-- Storage > New Bucket > Name: "sku-cache" > Public: OFF

-- ── Row Level Security (opcional para equipa) ───────────────────────────────
-- ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
-- Por agora deixamos aberto com a anon key (acesso controlado pela app)
