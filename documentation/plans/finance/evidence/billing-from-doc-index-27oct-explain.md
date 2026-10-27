# BILLING-FROM-DOC-INDEX: EXPLAIN ANALYZE before / after (sandbox)

Sandbox Postgres 16, `scripts.bootstrap_env` schema, seeded 30,000 `finance.billing_documents` (3 companies) and 300,000 `finance.billing_document_lines` (1/3 from a DO, 1/3 from an SO, 1/3 neither). Query = the real `document_relations` SELECT, compiled with literal binds, wrapped as `SELECT id FROM billing_documents WHERE id IN (...)`. "Before" = `alembic downgrade -1` (no index); "after" = `alembic upgrade head` (bfd_idx_0001_billing_from_doc_no).

| Lookup | Before | After |
| --- | --- | --- |
| DO Invoices (`billing_ids_for_delivery_order`) | 2 x Parallel Seq Scan on billing_document_lines, 40.7 ms | Index Scan using ix_finance_billing_document_lines_from_doc_no, 2.6 ms |
| SO Invoices (`billing_ids_for_sales_order`), OR form | 2 x Seq Scan, 121.4 ms | still 2 x Seq Scan, 81.6 ms (OR over IN-subqueries cannot use an index) |
| SO Invoices, UNION form (this PR) | - | Index Scans on from_doc_no + sales_order_line indexes, 7.1 ms |

## DO, before
```
Hash Join (actual time=40.494..40.595 rows=0 loops=1)
  Hash Cond: (billing_documents.id = billing_documents_1.id)
  ->  Seq Scan on billing_documents (actual time=0.004..0.004 rows=1 loops=1)
  ->  Hash (actual time=40.455..40.554 rows=0 loops=1)
        Buckets: 8192  Batches: 1  Memory Usage: 64kB
        ->  Bitmap Heap Scan on billing_documents billing_documents_1 (actual time=40.454..40.552 rows=0 loops=1)
              Recheck Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
              Filter: ((hashed SubPlan 1) OR (hashed SubPlan 2))
              Rows Removed by Filter: 10000
              Heap Blocks: exact=545
              ->  Bitmap Index Scan on ix_finance_billing_documents_company_id (actual time=0.226..0.226 rows=10000 loops=1)
                    Index Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
              SubPlan 1
                ->  Nested Loop (actual time=15.937..16.008 rows=0 loops=1)
                      ->  Gather (actual time=0.726..15.986 rows=1 loops=1)
                            Workers Planned: 2
                            Workers Launched: 2
                            ->  Parallel Seq Scan on billing_document_lines (actual time=7.840..12.867 rows=0 loops=3)
                                  Filter: (((from_doc_type)::text = 'DO'::text) AND ((from_doc_no)::text = 'DO-1234'::text))
                                  Rows Removed by Filter: 100000
                      ->  Index Scan using billing_documents_pkey on billing_documents billing_documents_2 (actual time=0.017..0.018 rows=0 loops=1)
                            Index Cond: (id = billing_document_lines.document_id)
                            Filter: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                            Rows Removed by Filter: 1
              SubPlan 2
                ->  Nested Loop (actual time=21.483..21.507 rows=0 loops=1)
                      ->  Gather (actual time=0.582..21.480 rows=1 loops=1)
                            Workers Planned: 2
                            Workers Launched: 2
                            ->  Parallel Seq Scan on billing_document_lines billing_document_lines_1 (actual time=8.768..14.944 rows=0 loops=3)
                                  Filter: (((from_doc_type)::text = 'DO'::text) AND ((from_doc_no)::text = 'DO-1234'::text))
                                  Rows Removed by Filter: 100000
                      ->  Index Scan using billing_documents_pkey on billing_documents billing_documents_3 (actual time=0.021..0.022 rows=0 loops=1)
                            Index Cond: (id = billing_document_lines_1.document_id)
                            Filter: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                            Rows Removed by Filter: 1
Planning Time: 1.096 ms
Execution Time: 40.695 ms
```
## DO, after
```
Hash Join (actual time=2.483..2.489 rows=0 loops=1)
  Hash Cond: (billing_documents.id = billing_documents_1.id)
  ->  Seq Scan on billing_documents (actual time=0.003..0.003 rows=1 loops=1)
  ->  Hash (actual time=2.447..2.451 rows=0 loops=1)
        Buckets: 8192  Batches: 1  Memory Usage: 64kB
        ->  Bitmap Heap Scan on billing_documents billing_documents_1 (actual time=2.446..2.450 rows=0 loops=1)
              Recheck Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
              Filter: ((hashed SubPlan 1) OR (hashed SubPlan 2))
              Rows Removed by Filter: 10000
              Heap Blocks: exact=545
              ->  Bitmap Index Scan on ix_finance_billing_documents_company_id (actual time=0.214..0.214 rows=10000 loops=1)
                    Index Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
              SubPlan 1
                ->  Nested Loop (actual time=0.041..0.043 rows=0 loops=1)
                      ->  Index Scan using ix_finance_billing_document_lines_from_doc_no on billing_document_lines (actual time=0.030..0.031 rows=1 loops=1)
                            Index Cond: ((from_doc_no)::text = 'DO-1234'::text)
                            Filter: ((from_doc_type)::text = 'DO'::text)
                      ->  Index Scan using billing_documents_pkey on billing_documents billing_documents_2 (actual time=0.010..0.010 rows=0 loops=1)
                            Index Cond: (id = billing_document_lines.document_id)
                            Filter: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                            Rows Removed by Filter: 1
              SubPlan 2
                ->  Nested Loop (actual time=0.014..0.015 rows=0 loops=1)
                      ->  Index Scan using ix_finance_billing_document_lines_from_doc_no on billing_document_lines billing_document_lines_1 (actual time=0.008..0.009 rows=1 loops=1)
                            Index Cond: ((from_doc_no)::text = 'DO-1234'::text)
                            Filter: ((from_doc_type)::text = 'DO'::text)
                      ->  Index Scan using billing_documents_pkey on billing_documents billing_documents_3 (actual time=0.005..0.005 rows=0 loops=1)
                            Index Cond: (id = billing_document_lines_1.document_id)
                            Filter: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                            Rows Removed by Filter: 1
Planning Time: 1.170 ms
Execution Time: 2.585 ms
```
## SO, UNION form, after
```
Hash Join (actual time=3.373..3.402 rows=0 loops=1)
  Hash Cond: (billing_documents.id = billing_documents_1.id)
  ->  Seq Scan on billing_documents (actual time=0.008..0.009 rows=1 loops=1)
  ->  Hash (actual time=3.320..3.347 rows=0 loops=1)
        Buckets: 8192  Batches: 1  Memory Usage: 64kB
        ->  Bitmap Heap Scan on billing_documents billing_documents_1 (actual time=3.319..3.345 rows=0 loops=1)
              Recheck Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
              Filter: ((hashed SubPlan 5) OR (hashed SubPlan 10))
              Rows Removed by Filter: 10000
              Heap Blocks: exact=545
              ->  Bitmap Index Scan on ix_finance_billing_documents_company_id (actual time=0.307..0.308 rows=10000 loops=1)
                    Index Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
              SubPlan 5
                ->  HashAggregate (actual time=0.143..0.157 rows=0 loops=1)
                      Group Key: billing_document_lines.document_id
                      Batches: 1  Memory Usage: 73kB
                      ->  Append (actual time=0.127..0.140 rows=0 loops=1)
                            ->  Hash Join (actual time=0.048..0.052 rows=0 loops=1)
                                  Hash Cond: (billing_documents_2.id = billing_document_lines.document_id)
                                  ->  Bitmap Heap Scan on billing_documents billing_documents_2 (never executed)
                                        Recheck Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                        ->  Bitmap Index Scan on ix_finance_billing_documents_company_id (never executed)
                                              Index Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                  ->  Hash (actual time=0.008..0.011 rows=0 loops=1)
                                        Buckets: 8192  Batches: 1  Memory Usage: 64kB
                                        ->  Nested Loop (actual time=0.008..0.009 rows=0 loops=1)
                                              ->  Index Scan using ix_sales_order_lines_sales_order_id on sales_order_lines sales_order_lines_1 (actual time=0.007..0.008 rows=0 loops=1)
                                                    Index Cond: (sales_order_id = '00000000-0000-0000-0002-000000000001'::uuid)
                                              ->  Index Scan using ix_finance_billing_document_lines_sales_order_line on billing_document_lines (never executed)
                                                    Index Cond: (sales_order_line_id = sales_order_lines_1.id)
                            ->  Nested Loop (actual time=0.064..0.066 rows=0 loops=1)
                                  ->  Index Scan using ix_finance_billing_document_lines_from_doc_no on billing_document_lines billing_document_lines_1 (actual time=0.043..0.045 rows=2 loops=1)
                                        Index Cond: ((from_doc_no)::text = 'SO-1234'::text)
                                        Filter: ((from_doc_type)::text = 'SO'::text)
                                  ->  Index Scan using billing_documents_pkey on billing_documents billing_documents_3 (actual time=0.009..0.009 rows=0 loops=2)
                                        Index Cond: (id = billing_document_lines_1.document_id)
                                        Filter: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                        Rows Removed by Filter: 1
                            ->  Nested Loop (actual time=0.013..0.018 rows=0 loops=1)
                                  ->  Nested Loop (actual time=0.012..0.016 rows=0 loops=1)
                                        ->  HashAggregate (actual time=0.011..0.015 rows=0 loops=1)
                                              Group Key: (orders.order_number)::text
                                              Batches: 1  Memory Usage: 24kB
                                              ->  Nested Loop (actual time=0.009..0.012 rows=0 loops=1)
                                                    ->  Index Scan using ix_orders_company_id on orders orders_1 (actual time=0.008..0.010 rows=0 loops=1)
                                                          Index Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                                          Filter: ((deleted_at IS NULL) AND (is_cancelled IS FALSE) AND ((sales_order_id = '00000000-0000-0000-0002-000000000001'::uuid) OR (hashed SubPlan 4)))
                                                          SubPlan 4
                                                            ->  Index Scan using ix_order_lines_company_from_doc_no on order_lines (never executed)
                                                                  Index Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                                                  Filter: ((((from_doc_no)::text = 'SO-1234'::text) AND ((from_doc_type IS NULL) OR ((from_doc_type)::text = 'SO'::text))) OR ((hashed SubPlan 3) AND ((from_doc_no IS NULL) OR ((from_doc_no)::text = 'SO-1234'::text))))
                                                                  SubPlan 3
                                                                    ->  Index Scan using ix_sales_order_lines_sales_order_id on sales_order_lines (never executed)
                                                                          Index Cond: (sales_order_id = '00000000-0000-0000-0002-000000000001'::uuid)
                                                    ->  Index Scan using orders_pkey on orders (never executed)
                                                          Index Cond: (id = orders_1.id)
                                        ->  Index Scan using ix_finance_billing_document_lines_from_doc_no on billing_document_lines billing_document_lines_2 (never executed)
                                              Index Cond: ((from_doc_no)::text = (orders.order_number)::text)
                                              Filter: ((from_doc_type)::text = 'DO'::text)
                                  ->  Index Scan using billing_documents_pkey on billing_documents billing_documents_4 (never executed)
                                        Index Cond: (id = billing_document_lines_2.document_id)
                                        Filter: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
              SubPlan 10
                ->  HashAggregate (actual time=0.067..0.078 rows=0 loops=1)
                      Group Key: billing_document_lines_3.document_id
                      Batches: 1  Memory Usage: 73kB
                      ->  Append (actual time=0.060..0.070 rows=0 loops=1)
                            ->  Hash Join (actual time=0.037..0.040 rows=0 loops=1)
                                  Hash Cond: (billing_documents_5.id = billing_document_lines_3.document_id)
                                  ->  Bitmap Heap Scan on billing_documents billing_documents_5 (never executed)
                                        Recheck Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                        ->  Bitmap Index Scan on ix_finance_billing_documents_company_id (never executed)
                                              Index Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                  ->  Hash (actual time=0.004..0.006 rows=0 loops=1)
                                        Buckets: 8192  Batches: 1  Memory Usage: 64kB
                                        ->  Nested Loop (actual time=0.004..0.005 rows=0 loops=1)
                                              ->  Index Scan using ix_sales_order_lines_sales_order_id on sales_order_lines sales_order_lines_3 (actual time=0.004..0.004 rows=0 loops=1)
                                                    Index Cond: (sales_order_id = '00000000-0000-0000-0002-000000000001'::uuid)
                                              ->  Index Scan using ix_finance_billing_document_lines_sales_order_line on billing_document_lines billing_document_lines_3 (never executed)
                                                    Index Cond: (sales_order_line_id = sales_order_lines_3.id)
                            ->  Nested Loop (actual time=0.017..0.017 rows=0 loops=1)
                                  ->  Index Scan using ix_finance_billing_document_lines_from_doc_no on billing_document_lines billing_document_lines_4 (actual time=0.008..0.008 rows=2 loops=1)
                                        Index Cond: ((from_doc_no)::text = 'SO-1234'::text)
                                        Filter: ((from_doc_type)::text = 'SO'::text)
                                  ->  Index Scan using billing_documents_pkey on billing_documents billing_documents_6 (actual time=0.003..0.004 rows=0 loops=2)
                                        Index Cond: (id = billing_document_lines_4.document_id)
                                        Filter: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                        Rows Removed by Filter: 1
                            ->  Nested Loop (actual time=0.006..0.010 rows=0 loops=1)
                                  ->  Nested Loop (actual time=0.005..0.009 rows=0 loops=1)
                                        ->  HashAggregate (actual time=0.005..0.008 rows=0 loops=1)
                                              Group Key: (orders_2.order_number)::text
                                              Batches: 1  Memory Usage: 24kB
                                              ->  Nested Loop (actual time=0.004..0.007 rows=0 loops=1)
                                                    ->  Index Scan using ix_orders_company_id on orders orders_3 (actual time=0.004..0.005 rows=0 loops=1)
                                                          Index Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                                          Filter: ((deleted_at IS NULL) AND (is_cancelled IS FALSE) AND ((sales_order_id = '00000000-0000-0000-0002-000000000001'::uuid) OR (hashed SubPlan 9)))
                                                          SubPlan 9
                                                            ->  Index Scan using ix_order_lines_company_from_doc_no on order_lines order_lines_1 (never executed)
                                                                  Index Cond: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
                                                                  Filter: ((((from_doc_no)::text = 'SO-1234'::text) AND ((from_doc_type IS NULL) OR ((from_doc_type)::text = 'SO'::text))) OR ((hashed SubPlan 8) AND ((from_doc_no IS NULL) OR ((from_doc_no)::text = 'SO-1234'::text))))
                                                                  SubPlan 8
                                                                    ->  Index Scan using ix_sales_order_lines_sales_order_id on sales_order_lines sales_order_lines_2 (never executed)
                                                                          Index Cond: (sales_order_id = '00000000-0000-0000-0002-000000000001'::uuid)
                                                    ->  Index Scan using orders_pkey on orders orders_2 (never executed)
                                                          Index Cond: (id = orders_3.id)
                                        ->  Index Scan using ix_finance_billing_document_lines_from_doc_no on billing_document_lines billing_document_lines_5 (never executed)
                                              Index Cond: ((from_doc_no)::text = (orders_2.order_number)::text)
                                              Filter: ((from_doc_type)::text = 'DO'::text)
                                  ->  Index Scan using billing_documents_pkey on billing_documents billing_documents_7 (never executed)
                                        Index Cond: (id = billing_document_lines_5.document_id)
                                        Filter: (company_id = '00000000-0000-0000-0001-000000000001'::uuid)
Planning Time: 7.342 ms
Execution Time: 7.136 ms
```
