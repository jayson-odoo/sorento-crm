"""One customer per debtor code per company (CUSTOMER-CODE-IDENTITY).

Owner decision, 30 Sep 2026: AutoCount keys a debtor by code, but the CRM matched
customers on the (code, name) pair and back-created a row whenever a document
spelled the name differently - so 300-1001 existed three times, 300-4002 and
300-H030 twice, and the ingest resolver picked one at random. Four steps:

1. ``customers.name_aliases`` (jsonb list, default ``[]``): the names a customer
   has also been known by.
2. ``sales_orders.debtor_name``: the customer name the SO was issued under,
   per document (``orders`` already carries one).
3. **Merge** every duplicate-code group per company onto one survivor: the row
   holding the integration reference, else the one with the most orders
   (``orders`` + ``sales_orders``), else the oldest. Every FK referencing
   ``customers(id)`` is repointed - discovered from ``pg_constraint`` exactly as
   migration 220 did, so a child table added since needs no revision here. A
   child row that would collide with one the survivor already holds (the same
   Respond.io contact linked to both, the same customer_code map row) is
   dropped rather than duplicated; a loser's ``main`` contact becomes a
   ``stakeholder`` when the survivor already has a ``main``. Empty contact and
   classification columns on the survivor are filled from the losers (never
   overwritten). The losers' names go into ``name_aliases``, then the losers are
   deleted. DESTRUCTIVE: run only after the read-only report
   (``python -m scripts.report_customer_code_duplicates``) has been reviewed.
4. Replace ``uq_customers_company_code_name_lower`` with
   ``uq_customers_company_code_lower`` on ``(company_id, lower(btrim(customer_code)))``.

Revision ID: cci_0001_customer_code_identity
Revises: lsa_0001_show_all_counts
Create Date: 2026-09-30
"""
from __future__ import annotations

from alembic import op

revision = "cci_0001_customer_code_identity"
down_revision = "lsa_0001_show_all_counts"
branch_labels = None
depends_on = None

_OLD_INDEX = "uq_customers_company_code_name_lower"
_NEW_INDEX = "uq_customers_company_code_lower"

_MERGE_SQL = """
DO $do$
DECLARE
    grp RECORD;
    survivor_id uuid;
    loser RECORD;
    losing_ids uuid[];
    fk RECORD;
    child RECORD;
    alias_names jsonb;
BEGIN
    FOR grp IN
        SELECT company_id, lower(btrim(customer_code)) AS code_key
        FROM customers
        GROUP BY 1, 2
        HAVING count(*) > 1
    LOOP
        -- Survivor: the ref holder, else the most orders, else the oldest.
        SELECT c.id INTO survivor_id
        FROM customers c
        LEFT JOIN LATERAL (
            SELECT count(*) AS n FROM integration_references r
            WHERE r.entity_type = 'customers' AND r.entity_id = c.id::text
        ) refs ON true
        LEFT JOIN LATERAL (
            SELECT (SELECT count(*) FROM orders o WHERE o.customer_id = c.id)
                 + (SELECT count(*) FROM sales_orders s WHERE s.customer_id = c.id) AS n
        ) ords ON true
        WHERE c.company_id IS NOT DISTINCT FROM grp.company_id
          AND lower(btrim(c.customer_code)) = grp.code_key
        ORDER BY (refs.n > 0) DESC, ords.n DESC, c.created_at ASC NULLS LAST, c.id ASC
        LIMIT 1;

        SELECT array_agg(id ORDER BY created_at ASC NULLS LAST, id ASC) INTO losing_ids
        FROM customers
        WHERE company_id IS NOT DISTINCT FROM grp.company_id
          AND lower(btrim(customer_code)) = grp.code_key
          AND id <> survivor_id;

        IF losing_ids IS NULL OR array_length(losing_ids, 1) IS NULL THEN
            CONTINUE;
        END IF;

        -- The losers' names (and their own aliases) become the survivor's aliases,
        -- oldest first, distinct case/space-insensitively, never the current name.
        SELECT coalesce(name_aliases, '[]'::jsonb) INTO alias_names
        FROM customers WHERE id = survivor_id;
        FOR loser IN
            SELECT id, customer_name, coalesce(name_aliases, '[]'::jsonb) AS name_aliases,
                   email, phone_number, mobile_number, registered_name, trading_name,
                   registration_number, industry, website, billing_address, country,
                   tax_id, account_owner_user_id, market_segment_code, region,
                   sales_agent_id
            FROM customers
            WHERE id = ANY(losing_ids)
            ORDER BY created_at ASC NULLS LAST, id ASC
        LOOP
            FOR child IN
                SELECT value AS candidate
                FROM jsonb_array_elements_text(
                    jsonb_build_array(loser.customer_name) || loser.name_aliases
                )
            LOOP
                IF NOT EXISTS (
                    SELECT 1 FROM customers s
                    WHERE s.id = survivor_id
                      AND lower(btrim(s.customer_name)) = lower(btrim(child.candidate))
                ) AND NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(alias_names) a
                    WHERE lower(btrim(a.value)) = lower(btrim(child.candidate))
                ) THEN
                    alias_names := alias_names || jsonb_build_array(child.candidate);
                END IF;
            END LOOP;

            -- Fill-only: an empty survivor column takes the loser's value.
            UPDATE customers s SET
                email = coalesce(nullif(btrim(s.email), ''), loser.email),
                phone_number = coalesce(nullif(btrim(s.phone_number), ''), loser.phone_number),
                mobile_number = coalesce(nullif(btrim(s.mobile_number), ''), loser.mobile_number),
                registered_name = coalesce(nullif(btrim(s.registered_name), ''), loser.registered_name),
                trading_name = coalesce(nullif(btrim(s.trading_name), ''), loser.trading_name),
                registration_number = coalesce(nullif(btrim(s.registration_number), ''), loser.registration_number),
                industry = coalesce(nullif(btrim(s.industry), ''), loser.industry),
                website = coalesce(nullif(btrim(s.website), ''), loser.website),
                billing_address = coalesce(s.billing_address, loser.billing_address),
                country = coalesce(nullif(btrim(s.country), ''), loser.country),
                tax_id = coalesce(nullif(btrim(s.tax_id), ''), loser.tax_id),
                account_owner_user_id = coalesce(s.account_owner_user_id, loser.account_owner_user_id),
                market_segment_code = coalesce(s.market_segment_code, loser.market_segment_code),
                region = coalesce(nullif(btrim(s.region), ''), loser.region),
                sales_agent_id = coalesce(s.sales_agent_id, loser.sales_agent_id)
            WHERE s.id = survivor_id;
        END LOOP;
        UPDATE customers SET name_aliases = alias_names WHERE id = survivor_id;

        -- A loser's main contact steps down when the survivor already has one
        -- (uq_customer_contacts_one_main_per_customer).
        IF EXISTS (
            SELECT 1 FROM customer_contacts
            WHERE customer_id = survivor_id AND contact_role = 'main'
        ) THEN
            UPDATE customer_contacts SET contact_role = 'stakeholder'
            WHERE customer_id = ANY(losing_ids) AND contact_role = 'main';
        ELSE
            -- At most one main may move over: the oldest loser's.
            UPDATE customer_contacts SET contact_role = 'stakeholder'
            WHERE customer_id = ANY(losing_ids) AND contact_role = 'main'
              AND id <> (
                  SELECT cc.id FROM customer_contacts cc
                  JOIN customers c ON c.id = cc.customer_id
                  WHERE cc.customer_id = ANY(losing_ids) AND cc.contact_role = 'main'
                  ORDER BY c.created_at ASC NULLS LAST, c.id ASC, cc.created_at ASC
                  LIMIT 1
              );
        END IF;

        -- The survivor keeps its own origin. A loser's reference is dropped: by the
        -- survivor rule a loser can only hold one when the survivor holds one too,
        -- and one record has exactly one origin (uq_integration_ref_entity).
        DELETE FROM integration_references
        WHERE entity_type = 'customers' AND entity_id = ANY(losing_ids::text[]);

        -- Search embeddings of the losers (written by the ORM listener the raw
        -- DELETE below bypasses) go with them, or the chatbot keeps finding them.
        IF to_regclass('embedding_documents') IS NOT NULL THEN
            DELETE FROM embedding_documents
            WHERE source_type = 'customer' AND source_id = ANY(losing_ids::text[]);
        END IF;
        IF to_regclass('embedding_queue') IS NOT NULL THEN
            DELETE FROM embedding_queue
            WHERE source_type = 'customer' AND source_id = ANY(losing_ids::text[]);
        END IF;

        -- Re-point every FK referencing customers(id), discovered dynamically
        -- (migration 220's mechanism): one set-based UPDATE per child table, and
        -- only when a unique constraint refuses that (the survivor already holds
        -- the equivalent of some row) a per-row pass that drops exactly the rows
        -- that collide - they say nothing the survivor's own row does not. A
        -- person's contact record is never dropped that way: the main-contact
        -- demotion above is what makes contacts movable, so a collision there is
        -- a bug in that step and stops the migration instead of losing a contact.
        FOR fk IN
            SELECT c.conrelid::regclass::text AS child_table,
                   att.attname               AS child_column
            FROM pg_constraint c
            JOIN pg_attribute att
              ON att.attrelid = c.conrelid AND att.attnum = ANY (c.conkey)
            WHERE c.contype = 'f' AND c.confrelid = 'customers'::regclass
        LOOP
            BEGIN
                EXECUTE format(
                    'UPDATE %s SET %I = $1 WHERE %I = ANY($2)',
                    fk.child_table, fk.child_column, fk.child_column
                ) USING survivor_id, losing_ids;
            EXCEPTION WHEN unique_violation THEN
                IF fk.child_table = 'customer_contacts' THEN
                    RAISE;
                END IF;
                FOR child IN EXECUTE format(
                    'SELECT ctid AS row_ctid FROM %s WHERE %I = ANY($1)',
                    fk.child_table, fk.child_column
                ) USING losing_ids
                LOOP
                    BEGIN
                        EXECUTE format(
                            'UPDATE %s SET %I = $1 WHERE ctid = $2',
                            fk.child_table, fk.child_column
                        ) USING survivor_id, child.row_ctid;
                    EXCEPTION WHEN unique_violation THEN
                        EXECUTE format('DELETE FROM %s WHERE ctid = $1', fk.child_table)
                        USING child.row_ctid;
                    END;
                END LOOP;
            END;
        END LOOP;

        DELETE FROM customers WHERE id = ANY(losing_ids);
    END LOOP;
END
$do$;
"""


def upgrade() -> None:
    op.execute(
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS name_aliases jsonb "
        "NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute("ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS debtor_name varchar(255)")
    op.execute(_MERGE_SQL)
    op.execute(f"DROP INDEX IF EXISTS {_OLD_INDEX}")
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_NEW_INDEX} "
        "ON customers (company_id, lower(btrim(customer_code)))"
    )


def downgrade() -> None:
    # The merge is not reversible (the losers are gone); only the shape is.
    op.execute(f"DROP INDEX IF EXISTS {_NEW_INDEX}")
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_OLD_INDEX} ON customers "
        "(company_id, lower(btrim(customer_code)), lower(btrim(customer_name)))"
    )
    op.execute("ALTER TABLE sales_orders DROP COLUMN IF EXISTS debtor_name")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS name_aliases")
