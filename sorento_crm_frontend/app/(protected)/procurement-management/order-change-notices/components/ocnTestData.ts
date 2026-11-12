/**
 * Shared fake data for the Order Change Notice suites (OCN-ORDER-CHANGE-NOTICE). Test support only.
 *
 * The shapes are the backend's flat response (tests/_ocn_support.py: `change_type_name`, `risk_level`,
 * `guide_text` flat on list rows and detail; status values draft / submitted / resubmitted /
 * approved / rejected / processed_by_cs / voided; `approval_status` pending / approved / rejected).
 * All names, numbers and codes are invented.
 */

export const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

export const OCN_ID = '5b0a8c52-3f0d-4c61-9d51-1f2a7a0c9e01';
const PROJECT_ID = '0c4f1d7e-6a53-4e0b-8d0e-3c1b8f9a2d02';
const CUSTOMER_ID = '9e2d7b14-1c55-4a8f-b6a3-7d4e0f1c8b03';
const PRODUCT_1 = '3a9c5e21-7b64-4d18-9f02-5e8a1c7d4b04';
const PRODUCT_2 = '7d1e4a93-2c80-4b57-a1f6-9b3c6e0d5a05';
const SALES_USER = '2f6b9d38-5e41-4c97-8a20-4d7c1b0e6f06';
const CS_USER = '8c3a5f60-9d12-4e74-b3c8-0a5e2d1f7b07';

export const CHANGE_TYPES = [
  { id: 'c1d2e3f4-0001-4a00-8000-000000000001', name: 'Advance', risk_level: 'Low', guide_text: 'Advance: the customer wants it sooner. Check stock and the supplier date.', is_active: true },
  { id: 'c1d2e3f4-0002-4a00-8000-000000000002', name: 'Exchange', risk_level: 'High', guide_text: 'Exchange: check delivered stock and whether the supplier order can be switched.', is_active: true },
  { id: 'c1d2e3f4-0003-4a00-8000-000000000003', name: 'Cancellation', risk_level: 'Highest', guide_text: 'Cancellation: check what has been ordered from the supplier and what was delivered.', is_active: true },
  { id: 'c1d2e3f4-0004-4a00-8000-000000000004', name: 'Delay', risk_level: 'Low', guide_text: 'Delay: the site is not ready. Check the supplier date.', is_active: true },
];

export type FakeStatus =
  | 'draft'
  | 'submitted'
  | 'resubmitted'
  | 'approved'
  | 'rejected'
  | 'processed_by_cs'
  | 'voided';

export function ocnLine(over: Record<string, unknown> = {}) {
  return {
    id: '6e8b2a47-1d93-4c05-a7f1-2b9d4c6e8a08',
    position: 1,
    product_id: PRODUCT_1,
    product_code: 'ABC123-RL',
    product_name: 'ZZT tile ABC123-RL',
    qty_before: '842',
    qty_after: '0',
    date_before: '2027-01-15',
    date_after: '2027-01-15',
    delivered_qty: '12',
    remark: 'Collect back 12 sets',
    ...over,
  };
}

/** A list row: one OCN as the grid shows it. */
export function ocnRow(over: Record<string, unknown> = {}) {
  return {
    id: OCN_ID,
    ocn_number: 'OCN26-0302',
    ocn_date: '2026-11-03',
    customer_id: CUSTOMER_ID,
    customer_name: 'Customer A',
    customer_po_no: 'XT04/3871 (R1)',
    so_no_text: null,
    change_type_id: CHANGE_TYPES[1].id,
    change_type_name: 'Exchange',
    risk_level: 'High',
    project_id: PROJECT_ID,
    project_title: 'Project Alpha Tower',
    sales_in_charge_user_id: SALES_USER,
    sales_in_charge_name: 'Sales Person A',
    status: 'submitted',
    approval_status: null,
    revision_no: 0,
    source: 'crm',
    ...over,
  };
}

/** The detail record the page reads. */
export function ocnDetail(over: Record<string, unknown> = {}) {
  return {
    ...ocnRow(),
    id: OCN_ID,
    status: 'draft',
    approval_status: null,
    description: 'Customer replaces ABC123-RL with ABC123-SH, same delivery date.',
    cs_in_charge_user_id: CS_USER,
    cs_in_charge_name: 'CS Person A',
    guide_text: CHANGE_TYPES[1].guide_text,
    cs_comment: null,
    created_by: SALES_USER,
    created_by_name: 'Sales Person A',
    created_at: '2026-11-03T02:00:00',
    approver_id: null,
    approver_name: null,
    approved_at: null,
    approval_comments: null,
    lines: [
      ocnLine(),
      ocnLine({
        id: '1f4d7a90-8b26-4e3c-95d1-6c0a3b7e9d09',
        position: 2,
        product_id: PRODUCT_2,
        product_code: 'ABC123-SH',
        product_name: 'ZZT tile ABC123-SH',
        qty_before: '0',
        qty_after: '842',
        delivered_qty: '0',
        remark: 'Replacement',
      }),
    ],
    attachments: [],
    ...over,
  };
}

export const PRODUCT_HITS = [
  { id: PRODUCT_1, product_code: 'ABC123-RL', product_name: 'ZZT tile ABC123-RL', brand_name: 'ZZT' },
  { id: PRODUCT_2, product_code: 'ABC123-SH', product_name: 'ZZT tile ABC123-SH', brand_name: 'ZZT' },
];
