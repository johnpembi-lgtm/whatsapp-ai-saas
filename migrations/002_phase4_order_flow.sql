-- ====================================================================
-- MIGRATION PHASE 4 : FLUX DE COMMANDE, LIVRAISON/RETRAIT & STOCK
-- ====================================================================

-- 1. Configuration du Tenant (Livraison, Retrait & Politique de Stock)
ALTER TABLE tenants 
ADD COLUMN IF NOT EXISTS delivery_enabled BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS pickup_enabled BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS stock_policy VARCHAR(50) DEFAULT 'manual';

-- 2. Gestion du Stock dans les Produits
ALTER TABLE products 
ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT 0;

-- 3. Métadonnées Avancées de Commande (Livraison, Localisation & Idempotence)
ALTER TABLE orders 
ADD COLUMN IF NOT EXISTS fulfillment_type VARCHAR(20) CHECK (fulfillment_type IN ('delivery', 'pickup')),
ADD COLUMN IF NOT EXISTS delivery_address TEXT,
ADD COLUMN IF NOT EXISTS delivery_latitude NUMERIC,
ADD COLUMN IF NOT EXISTS delivery_longitude NUMERIC,
ADD COLUMN IF NOT EXISTS delivery_location_name TEXT,
ADD COLUMN IF NOT EXISTS external_reference VARCHAR(255) UNIQUE,
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

-- 4. Index de Performance
CREATE INDEX IF NOT EXISTS idx_orders_fulfillment ON orders(tenant_id, fulfillment_type);
CREATE INDEX IF NOT EXISTS idx_orders_external_ref ON orders(external_reference);