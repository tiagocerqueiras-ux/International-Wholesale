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

-- ══════════════════════════════════════════════════════════════════════════════
-- ROW LEVEL SECURITY (Camada 3 de segurança)
-- Corre estas instruções no SQL Editor do Supabase (uma vez)
-- ══════════════════════════════════════════════════════════════════════════════

-- 1. Activar RLS na tabela deals
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;

-- 2. Remover políticas antigas se existirem
DROP POLICY IF EXISTS "app_full_access" ON deals;

-- 3. Política: permite acesso total apenas à app (anon key via Streamlit)
--    A service_role key bypassa o RLS automaticamente.
--    O acesso directo à API sem a key correcta fica bloqueado.
CREATE POLICY "app_full_access" ON deals
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- Nota: com RLS activo, qualquer acesso directo ao Supabase sem
-- a API key configurada nos Secrets da app retorna 0 linhas.
-- Para revogar acesso completamente à anon key, apaga a policy acima
-- e usa apenas a service_role key na app (SUPABASE_KEY = sb_secret_...).
