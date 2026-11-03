import type { QuotationSignColumn } from '../../services/quotationSignService';

/**
 * Test fixture only: what the server sends as `scope.columns` for a scope with no product photo
 * (backend `app/services/quotation_columns.py`). The page itself keeps no column list.
 */
export const SIGN_COLUMNS: QuotationSignColumn[] = [
  { key: 'item', label: 'ITEM' },
  { key: 'spec', label: 'TECHNICAL SPEC' },
  { key: 'description', label: 'DESCRIPTION' },
  { key: 'brand', label: 'BRAND' },
  { key: 'product_code', label: 'PRODUCT CODE' },
  { key: 'qty', label: 'QTY' },
  { key: 'unit_rate', label: 'UNIT RATE (RM)' },
  { key: 'complete_set', label: 'COMPLETE SET' },
  { key: 'amount', label: 'GRAND TOTAL' },
];

/** The same, for a scope where a line carries a product photo. */
export const SIGN_COLUMNS_WITH_IMAGE: QuotationSignColumn[] = [
  SIGN_COLUMNS[0],
  { key: 'image', label: 'PRODUCT IMAGE' },
  ...SIGN_COLUMNS.slice(1),
];
