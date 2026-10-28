/**
 * PORTAL-P4-REQUESTS R1 test support: a fake `/api/v1/my-requests` backend for tests that render the
 * portal's SubmissionForm inside a CRM page. Records every call; answers with the portal's shapes.
 */
export interface ApiCall {
  url: string;
  method: string;
  body: unknown;
}

export const json = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });

export const ME = {
  contact_id: 'c1',
  space_id: 'sp1',
  name: 'Ann Sales',
  phone_number: '60123456789',
  expires_at: '2030-01-01T00:00:00Z',
};

export function createCrmApi(kind: 'stock_inquiry' | 'complaint', detail: () => Record<string, unknown>) {
  const calls: ApiCall[] = [];
  const handler = async (url: string, init?: RequestInit): Promise<Response> => {
    const method = (init?.method ?? 'GET').toUpperCase();
    let body: unknown = init?.body;
    if (typeof body === 'string') {
      try {
        body = JSON.parse(body);
      } catch {
        /* keep the string */
      }
    }
    calls.push({ url, method, body });
    const path = url.split('?')[0];
    if (path === '/api/v1/my-requests/me') return json({ ...ME });
    if (path === '/api/v1/my-requests/lookups/products')
      return json([{ product_code: 'PRD-1', product_name: 'Product One', category_id: null }]);
    if (path === '/api/v1/my-requests/lookups/debtors')
      return json([{ customer_id: 'd1', debtor_name: 'Debtor One', customer_code: 'D-1', sales_type: null }]);
    if (path === '/api/v1/my-requests/lookups/delivery-orders')
      return json([
        {
          order_number: 'DO-1',
          debtor_name: 'Debtor One',
          customer_name: 'Debtor One',
          products: ['PRD-1'],
          product_lines: [{ product_code: 'PRD-1', product_name: 'Product One', quantity: 2 }],
        },
      ]);
    if (path.startsWith('/api/v1/my-requests/lookups/sets/'))
      return json({ options: [{ value: 'opt-a', label: 'Option A' }], default_value: null });
    if (path === '/api/v1/my-requests/attachments' && method === 'POST')
      return json({ link_id: 'l1', attachment_id: 'a1', filename: 'f.pdf', size: 3, url: 'https://cdn/f.pdf', uploader_kind: 'contact', can_unlink: true });
    if (path.endsWith('/neighbours')) return json({ prev_id: null, next_id: null, position: 1, total: 1 });
    if (path.endsWith('/revisions') || path.endsWith('/comments')) return json({ items: [] });
    if (path.startsWith(`/api/v1/my-requests/submissions/${kind}`)) {
      if (path.endsWith('/submit')) return json({ ...detail(), status: 'pending_purchasing', is_draft: false });
      return json({ ...detail(), id: detail().id ?? 'new-1' });
    }
    if (path === '/api/v1/my-requests/requestor-options') return json({ items: [{ id: 'c1', name: 'Ann Sales' }], has_more: false });
    return json({});
  };
  return { calls, handler };
}

export const SI_DETAIL = (over: Record<string, unknown> = {}) => ({
  id: 'si-5',
  kind: 'stock_inquiry',
  title: 'Stock inquiry',
  reference: 'SI-2026-0005',
  status: 'draft',
  is_draft: true,
  is_editable: true,
  created_at: '2026-07-20T00:00:00Z',
  revision_no: 0,
  product_code: 'PRD-1',
  item_description: 'desc',
  quantity: '2',
  delivery_date: '2026-12-01',
  project_customer: 'Debtor One',
  project_name: 'Proj',
  salesperson_contact_id: 'c1',
  salesperson: 'Ann Sales',
  attachments: [],
  revision: { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null },
  ...over,
});

export const CMP_DETAIL = (over: Record<string, unknown> = {}) => ({
  id: 'cp-5',
  kind: 'complaint',
  title: 'Complaint',
  reference: 'CMP-2026-0005',
  status: 'draft',
  is_draft: true,
  is_editable: true,
  created_at: '2026-07-20T00:00:00Z',
  revision_no: 0,
  delivery_order_number: 'DO-1',
  customer_name: 'Debtor One',
  contact_person: 'Bob',
  contact_number: '0123',
  complaint_date: '2026-07-01',
  salesperson: 'Ann Sales',
  attachments: [],
  products: [{ product_code: 'PRD-1', product_type: 'x', quantity: '1' }],
  revision: { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null },
  ...over,
});
