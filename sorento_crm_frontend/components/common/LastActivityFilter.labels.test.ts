/**
 * FORMS-LAST-ACTIVITY crew browser pass: the column is "Last activity" everywhere (header and Columns menu
 * share meta.headerTitle), never "Last Activity".
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const LISTS = [
  'complaint-management/complaints/components/ComplaintsList.tsx',
  'procurement-management/purchase-requests/components/PurchaseRequestsList.tsx',
  'dealer-kit/price-tag-requests/components/PriceTagRequestsList.tsx',
  'project-sales/sample-requests/components/SampleRequestsList.tsx',
  'procurement-management/new-product-applications/components/NewProductApplicationsList.tsx',
  'procurement-management/stock-inquiries/components/StockInquiriesList.tsx',
  'workflow-forms-management/components/WorkflowSubmissionsList.tsx',
];

describe('Last activity label', () => {
  it.each(LISTS)('%s names the column exactly "Last activity"', (file) => {
    const src = readFileSync(`app/(protected)/${file}`, 'utf8');
    expect(src).toContain("headerTitle: 'Last activity'");
    expect(src).not.toContain('Last Activity');
  });
});
