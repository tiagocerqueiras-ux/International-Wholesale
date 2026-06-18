-- ============================================================================
-- MIGRAÇÃO FASE 1 — Produção (Supabase projeto suhbpfygvmgijztsfkyu)
-- ============================================================================
-- Correr UMA vez no SQL Editor do Supabase de PRODUÇÃO antes (ou em conjunto)
-- com o deploy do branch `fase1`.
--
-- É 100% ADITIVO e idempotente (ADD COLUMN IF NOT EXISTS): não altera nem apaga
-- nada do existente. O código antigo ignora estas colunas → "rollback" do schema
-- é não fazer nada (as colunas ficam inertes).
--
-- ⚠️ NÃO correr enquanto o IT estiver a bloquear a rede / sem acesso à conta
--    Supabase de produção. Requer login no SQL Editor desse projeto.
-- ============================================================================

-- ── Tabela clients: 13 campos novos de onboarding ───────────────────────────
ALTER TABLE clients
  ADD COLUMN IF NOT EXISTS commercial_cert_doc TEXT,
  ADD COLUMN IF NOT EXISTS fin_contact_name    TEXT,
  ADD COLUMN IF NOT EXISTS fin_contact_email   TEXT,
  ADD COLUMN IF NOT EXISTS fin_contact_phone   TEXT,
  ADD COLUMN IF NOT EXISTS billing_email       TEXT,
  ADD COLUMN IF NOT EXISTS iban                TEXT,
  ADD COLUMN IF NOT EXISTS swift               TEXT,
  ADD COLUMN IF NOT EXISTS bank_proof_doc      TEXT,
  ADD COLUMN IF NOT EXISTS credit_insurance    TEXT,
  ADD COLUMN IF NOT EXISTS credit_limit        NUMERIC,
  ADD COLUMN IF NOT EXISTS ubos                JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS delivery_addresses  JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS documents           JSONB DEFAULT '[]'::jsonb;

-- ── Tabela deals: ligação ao cliente + operador(es) logístico(s) ────────────
-- (supplier_ids pode já existir de uma migração anterior — IF NOT EXISTS protege)
ALTER TABLE deals
  ADD COLUMN IF NOT EXISTS client_id    TEXT,
  ADD COLUMN IF NOT EXISTS supplier_ids TEXT;

-- ── Verificação rápida (opcional) ───────────────────────────────────────────
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'clients'
--   AND column_name IN ('iban','ubos','delivery_addresses','documents');
