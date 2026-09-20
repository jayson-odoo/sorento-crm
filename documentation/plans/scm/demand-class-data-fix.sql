-- Demand class data fix. DRAFT, owner-run. Ends in ROLLBACK: read the counts, then swap to COMMIT.
-- Dry-run counts below are from the local copy sorento_ai_automation_0918_1900 (20 Sep 2026).
-- Ingest is fill-only on customers.market_segment_code, so these hand-set values survive every push.

BEGIN;

-- ---------------------------------------------------------------------------
-- A. Customers whose AutoCount name says "(PROJECT)" get segment = project.
--    Expect 474 rows (165 were 'retail', 309 were blank). Today NO customer is 'project'.
-- ---------------------------------------------------------------------------
UPDATE customers
   SET market_segment_code = 'project', updated_at = now()
 WHERE customer_name ILIKE '%(PROJECT)%'
   AND coalesce(market_segment_code, '') <> 'project';

-- A2. Their orders still stamped retail. Expect 2, both closed, both sold by a retail agent,
--     so under the ladder (agent above customer) they are CORRECT. Left alone on purpose.

-- ---------------------------------------------------------------------------
-- B. Agent LCL: stop the agent rung answering, let the customer decide.
--    ONLY run B if you choose this route. Run B1 -> B2 -> B3 -> B4 together.
-- ---------------------------------------------------------------------------

-- B1. Intercompany customers = project.
UPDATE customers
   SET market_segment_code = 'project', updated_at = now()
 WHERE customer_code IN ('303-I001',   -- IDEAL BATH SDN BHD            (was blank)
                         '303-N001')   -- NAUTICAL SANITARYWARE SDN BHD (was blank)
    OR customer_name ILIKE 'BEYOND BATH SDN BHD%';             -- was 'retail'; CHECK the match list first:
-- SELECT customer_code, customer_name, market_segment_code FROM customers WHERE customer_name ILIKE 'BEYOND BATH%';

-- B2. LCL customers with a BLANK segment must state one, or the weekly upload refuses the file
--     once LCL stops answering. Defaulted to retail here; EDIT any that are really project.
UPDATE customers
   SET market_segment_code = 'retail', updated_at = now()
 WHERE coalesce(trim(market_segment_code), '') = ''
   AND customer_code IN ('300-S209',  -- SYNTALUN MARKETING PLT
                         '303-K003',  -- KEDAI CAT BOON SENG SDN BHD (SRT)
                         '303-K002',  -- KEDAI CAT BOON SENG SDN BHD (CERAMIC & ELLECI)
                         '300-C109',  -- CT BATHWORLD SDN BHD [A/C IV]
                         '301-C017',  -- CASH (MR LOO)
                         '300-L119',  -- LAVATOS SDN BHD (SRT)
                         '301-E017',  -- EONG HUAT CORPORATION SDN BHD
                         '300-H051',  -- HUE HOME APPLIANCES SDN BHD
                         '300-H120',  -- HUE HOME APPLIANCES SDN BHD (SRT)
                         '303-M002',  -- MBS TOOLS SDN BHD
                         '303-M003'); -- MBS HOME DECORATIONS SDN BHD

-- B3. Clear LCL's own class (same effect as blanking it on the Sales Agents screen).
UPDATE sales_agents SET demand_class = NULL, updated_at = now() WHERE sales_agent = 'LCL';

-- B4. Re-stamp LCL's existing orders from the customer segment. A stored class is never
--     re-decided by the app, so this is the only thing that moves PSM / SYNTALUN / MOCHA etc.
--     Rows with a stated order_type are skipped (order type outranks everything).
--     Drop the status filter's comment to limit this to open orders only.
UPDATE public.sales_orders so
   SET demand_class = CASE WHEN c.market_segment_code = 'project' THEN 'project' ELSE 'retail' END,
       updated_at = now()
  FROM customers c, sales_agents a
 WHERE c.id = so.customer_id
   AND a.id = so.sales_agent_id
   AND a.sales_agent = 'LCL'
   AND coalesce(trim(so.order_type), '') = ''
   AND coalesce(trim(c.market_segment_code), '') <> ''
   -- AND so.status = 'open'
   AND so.demand_class IS DISTINCT FROM
       CASE WHEN c.market_segment_code = 'project' THEN 'project' ELSE 'retail' END;

-- Verify before committing.
SELECT left(c.customer_name, 45) customer, c.market_segment_code seg, so.demand_class,
       count(*) n, count(*) FILTER (WHERE so.status = 'open') open_n
  FROM public.sales_orders so
  JOIN sales_agents a ON a.id = so.sales_agent_id
  LEFT JOIN customers c ON c.id = so.customer_id
 WHERE a.sales_agent = 'LCL'
 GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 30;

ROLLBACK;  -- swap to COMMIT once the counts read right
