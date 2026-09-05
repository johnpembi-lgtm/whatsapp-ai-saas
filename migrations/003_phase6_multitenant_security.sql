-- ============================================================================
-- MIGRATION 003
-- PEMBI - Phase 6.9
-- Durcissement multi-tenant : contraintes, index, RPC stock
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. IDEMPOTENCE DES COMMANDES PAR TENANT
-- ============================================================================

-- Retirer les anciennes contraintes globales éventuelles
ALTER TABLE public.orders
    DROP CONSTRAINT IF EXISTS orders_external_reference_key,
    DROP CONSTRAINT IF EXISTS unique_external_reference,
    DROP CONSTRAINT IF EXISTS uq_orders_tenant_external_ref;

-- Une même référence peut exister chez deux boutiques, mais pas deux fois dans la même
ALTER TABLE public.orders
    ADD CONSTRAINT uq_orders_tenant_external_ref
    UNIQUE (tenant_id, external_reference);

-- ============================================================================
-- 2. CUSTOMERS
-- ============================================================================
-- La contrainte canonique existe déjà depuis Phase 1 :
-- unique_tenant_customer_phone UNIQUE (tenant_id, phone)
-- On ne la recrée donc pas.

-- ============================================================================
-- 3. INDEX MULTI-TENANT
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_orders_tenant_customer
    ON public.orders (tenant_id, customer_id);

CREATE INDEX IF NOT EXISTS idx_orders_tenant_status
    ON public.orders (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_messages_tenant_conv
    ON public.messages (tenant_id, conversation_id);

CREATE INDEX IF NOT EXISTS idx_carts_tenant_customer
    ON public.carts (tenant_id, customer_id);

CREATE INDEX IF NOT EXISTS idx_products_tenant_active
    ON public.products (tenant_id, active);

CREATE INDEX IF NOT EXISTS idx_products_tenant_id
    ON public.products (tenant_id, id);

CREATE INDEX IF NOT EXISTS idx_conversations_tenant_customer
    ON public.conversations (tenant_id, customer_id);

-- ============================================================================
-- 4. RPC SECURISEE : complete_order_and_decrement_stock
-- ============================================================================

DROP FUNCTION IF EXISTS public.complete_order_and_decrement_stock(uuid);
DROP FUNCTION IF EXISTS public.complete_order_and_decrement_stock(uuid, uuid);

CREATE OR REPLACE FUNCTION public.complete_order_and_decrement_stock(
    p_order_id uuid,
    p_tenant_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $function$
DECLARE
    v_order RECORD;
    v_item RECORD;
    v_current_stock INTEGER;
BEGIN

    -- ------------------------------------------------------------------------
    -- A. Verrouiller UNIQUEMENT la commande appartenant au tenant
    -- ------------------------------------------------------------------------

    SELECT *
    INTO v_order
    FROM public.orders
    WHERE id = p_order_id
      AND tenant_id = p_tenant_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'message', 'Commande introuvable ou non autorisée'
        );
    END IF;

    -- ------------------------------------------------------------------------
    -- B. Idempotence du stock (Gestion du re-passing completed)
    -- ------------------------------------------------------------------------

    IF v_order.stock_applied_at IS NOT NULL THEN

        -- Si la commande n'est plus marquée 'completed' mais que le stock a déjà été appliqué,
        -- on restaure simplement l'état 'completed' sans redécrémenter.
        IF v_order.status <> 'completed' THEN
            UPDATE public.orders
            SET status = 'completed',
                completed_at = COALESCE(completed_at, NOW())
            WHERE id = p_order_id
              AND tenant_id = p_tenant_id;
        END IF;

        RETURN jsonb_build_object(
            'success', true,
            'message', 'Commande déjà finalisée, stock déjà appliqué'
        );
    END IF;

    -- ------------------------------------------------------------------------
    -- C. Vérifier et décrémenter chaque produit du tenant
    -- ------------------------------------------------------------------------

    FOR v_item IN
        SELECT oi.*
        FROM public.order_items oi
        WHERE oi.order_id = p_order_id
    LOOP

        SELECT p.stock
        INTO v_current_stock
        FROM public.products p
        WHERE p.id = v_item.product_id
          AND p.tenant_id = p_tenant_id
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Produit % introuvable pour ce tenant',
                v_item.product_id;
        END IF;

        IF v_current_stock < v_item.quantity THEN
            RAISE EXCEPTION
                'Stock insuffisant pour le produit % (Disponible: %, Requis: %)',
                v_item.product_id,
                v_current_stock,
                v_item.quantity;
        END IF;

        UPDATE public.products
        SET stock = stock - v_item.quantity
        WHERE id = v_item.product_id
          AND tenant_id = p_tenant_id;

    END LOOP;

    -- ------------------------------------------------------------------------
    -- D. Finalisation de la commande et horodatage de l'application du stock
    -- ------------------------------------------------------------------------

    UPDATE public.orders
    SET status = 'completed',
        completed_at = COALESCE(completed_at, NOW()),
        stock_applied_at = NOW()
    WHERE id = p_order_id
      AND tenant_id = p_tenant_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Commande complétée et stock appliqué'
    );

EXCEPTION
    WHEN OTHERS THEN
        RETURN jsonb_build_object(
            'success', false,
            'message', SQLERRM
        );
END;
$function$;

COMMIT;