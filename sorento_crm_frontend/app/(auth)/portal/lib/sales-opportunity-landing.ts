/**
 * Sales opportunities adapted into the landing's summary shape (fix lane round 2, F1), the
 * same way `listRequestsAsSummaries` adapts price tag requests, so the kind shares the one
 * selector, card, list, filter and sort every other kind uses.
 *
 * The opportunity list route takes no search term (an agent holds tens of rows, not
 * thousands), so the landing's search is applied here, over the fields a card shows.
 */
import type { PortalSubmissionSummary } from './portal-client';
import { listPortalSalesOpportunities } from './sales-opportunity-service';

export async function listOpportunitiesAsSummaries(q?: string): Promise<PortalSubmissionSummary[]> {
  const rows = await listPortalSalesOpportunities();
  const needle = (q ?? '').trim().toLowerCase();
  return rows
    .map((r) => ({
      id: r.id,
      kind: 'sales_opportunity' as const,
      title: r.title,
      document_number: r.opportunity_no,
      reference: null,
      status: r.outcome === 'open' ? r.stage_key : r.outcome,
      status_label: r.stage_label,
      is_editable: r.outcome === 'open',
      is_draft: false,
      created_at: (r as { created_at?: string | null }).created_at ?? null,
      customer_name: r.customer_name ?? r.prospect_name,
      expected_amount: r.expected_amount,
      expected_close_date: r.expected_close_date,
    }))
    .filter(
      (row) =>
        !needle ||
        [row.title, row.document_number, row.customer_name, row.status_label].some((v) =>
          (v ?? '').toLowerCase().includes(needle),
        ),
    );
}
