/**
 * Phase 1 fixture for the cross-project order inquiry.
 *
 * Shaped off the spreadsheet purchasing works from today (`JAN - DEC 2026 ORDER.xlsx`,
 * sheets `JAN 26`, `2.1.26`, ...): a row that traces to a placed purchase order carries
 * a supplier and a PO number, and one that does not carries neither, because on their
 * sheet a blank in those two columns is what "not placed yet" looks like.
 *
 * Kept after the backend landed because the component tests read from it: one shape for
 * the prototype and the tests means a test cannot pass against a row the screen never saw.
 */
import type {
  OrderInquiryWorklistRow,
  OrderInquiryWorklistSummary,
} from '../types/orderInquiry.types';

export const MOCK_WORKLIST_ROWS: OrderInquiryWorklistRow[] = [
  {
    id: 'row-1',
    so_date: '2025-12-30',
    so_number: 'SO385126',
    item_code: 'SRTWB5400',
    product_name: 'Wall hung basin 5400',
    qty: '35',
    delivery_date: '2026-01-02',
    project_customer: 'EXACO / CURVO RESIDENCE @ SETAPAK',
    supplier: 'DAFUYUAN',
    supplier_id: 'sup-1',
    po_number: '202601-S0015',
    state: 'actioned',
    raised_at: '2026-01-02T09:15:00',
    verb: 'ORDER',
    note: null,
    project_id: null,
    project_sales_order_id: 'pso-1',
    core_sales_order_id: 'so-385126',
    is_adopted: true,
  },
  {
    id: 'row-2',
    so_date: '2026-01-08',
    so_number: 'SO386461',
    item_code: 'SRTWC8605-SC-RL',
    product_name: 'Close coupled WC 8605',
    qty: '85',
    delivery_date: '2026-01-19',
    project_customer: 'OPTAD / ENG CONSTRUCTION / SEPANG',
    supplier: null,
    supplier_id: null,
    po_number: null,
    state: 'raised',
    raised_at: '2026-01-08T11:02:00',
    verb: 'ORDER',
    note: null,
    project_id: null,
    project_sales_order_id: 'pso-2',
    core_sales_order_id: 'so-386461',
    is_adopted: true,
  },
  {
    id: 'row-3',
    so_date: '2025-08-15',
    so_number: 'SO363150',
    item_code: 'SRTWT107',
    product_name: 'Wall hung WC 107',
    qty: '91',
    delivery_date: '2026-03-02',
    project_customer: 'KNUSFORD / EKO TITIWANGSA / KL',
    supplier: 'CHAOSHENG',
    supplier_id: 'sup-2',
    po_number: '202601-S0044',
    state: 'raised',
    raised_at: '2026-01-02T09:15:00',
    verb: 'ORDER',
    note: null,
    project_id: 'proj-9',
    project_sales_order_id: 'pso-3',
    core_sales_order_id: null,
    is_adopted: false,
  },
  {
    id: 'row-4',
    so_date: null,
    so_number: 'PSO-000412',
    item_code: 'BT012-CR',
    product_name: 'Bath trap chrome',
    qty: '6',
    delivery_date: null,
    project_customer: 'BUIMACO / INTA BINA / SDB @ GOMBAK',
    supplier: null,
    supplier_id: null,
    po_number: null,
    state: 'cancelled',
    raised_at: '2026-01-08T11:02:00',
    verb: 'CANCEL_BALANCE',
    note: 'Placed 12, new need 6',
    project_id: 'proj-4',
    project_sales_order_id: 'pso-4',
    core_sales_order_id: null,
    is_adopted: false,
  },
];

export const MOCK_WORKLIST_SUMMARY: OrderInquiryWorklistSummary = {
  total_rows: 4,
  total_qty: '217',
  by_state: { raised: 2, actioned: 1, cancelled: 1, total: 4 },
  by_month: [
    { month: '2026-01', label: 'JAN 26', rows: 2, qty: '120' },
    { month: '2026-03', label: 'MAR 26', rows: 1, qty: '91' },
  ],
  suppliers: [
    { id: 'sup-2', label: 'CHAOSHENG', rows: 1 },
    { id: 'sup-1', label: 'DAFUYUAN', rows: 1 },
  ],
  projects: [
    { id: 'proj-4', label: 'SDB @ Gombak', rows: 1 },
    { id: 'proj-9', label: 'Eko Titiwangsa', rows: 1 },
  ],
};
