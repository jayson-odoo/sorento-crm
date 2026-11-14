/**
 * R4 / G-1 - no NEW single-select filter in a list toolbar; the allowlist only shrinks
 *
 * UI v2 phase 0 (UAC G-1, rule R4). Every dropdown filter on a list is multi-select in v2
 * (`SearchableMultiSelect`). The detector is deliberately simple: a non-test file under app or components that
 * BOTH renders `<DataGridListToolbar` AND renders a single-select `<SearchableSelect` (the multi variant is
 * `<SearchableMultiSelect`, which does not match). Known limits: the toolbar and its filter can live in
 * different files (not caught), and a file can hold a single-select that is a form field and not a filter (a
 * false positive that stays in the allowlist until its wave touches the file). Both limits are acceptable for a
 * shrink-only guard. Reason for every entry: "v1, retires per R4 wave". Comments are stripped first.
 *
 * Same shape as components/ui/raw-table.inventory.test.ts: a source scan, an allowlist of path to reason, and a
 * stale-entry test so the list cannot rot. A new offender fails the first test; a fixed file must leave the
 * allowlist or the second test fails.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ROOTS = ['app', 'components'];

const REASON = 'v1, retires per R4 wave';

const TOOLBAR = /<DataGridListToolbar\b/;
const SINGLE_SELECT = /<SearchableSelect\b/;
const matches = (src: string) => TOOLBAR.test(src) && SINGLE_SELECT.test(src);
/** The toolbar's own definition is not a list that uses it. */
const EXCLUDED_FILES = ['components/ui/data-grid-list-toolbar.tsx'];

/** Every `.ts` and `.tsx` under the roots, tests and `.d.ts` excluded. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const rel = full.split(path.sep).join('/');
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(full);
      } else if (
        (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) &&
        !entry.name.endsWith('.d.ts') &&
        !/\.(test|spec)\./.test(entry.name) &&
        !EXCLUDED_FILES.includes(rel)
      ) {
        out.push(rel);
      }
    }
  };
  for (const root of ROOTS) walk(root);
  return out;
}

/** Drop block and line comments so prose that names the pattern is not an offender. */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"`])\/\/[^\n]*/g, '$1');
}

const readStripped = (file: string) =>
  stripComments(fs.readFileSync(file, 'utf8'));

/** Every current file that renders DataGridListToolbar with a single-select SearchableSelect, each with a one-line reason. Shrink-only. */
const ALLOWLIST: Record<string, string> = {
  'app/(protected)/forms-management/forms/components/FormsList.tsx': REASON,
  'app/(protected)/marketing-management/promotions/components/PromotionsList.tsx':
    REASON,
  'app/(protected)/master-data-management/brands/components/BrandsList.tsx':
    REASON,
  'app/(protected)/master-data-management/certificates/components/CertificateLinksList.tsx':
    REASON,
  'app/(protected)/master-data-management/certificates/components/CertificatesList.tsx':
    REASON,
  'app/(protected)/master-data-management/costing/components/CostingView.tsx':
    REASON,
  'app/(protected)/master-data-management/products/components/ProductsList.tsx':
    REASON,
  'app/(protected)/master-data-management/sales-agents/components/SalesAgentsList.tsx':
    REASON,
  'app/(protected)/order-management/branches/components/BranchesList.tsx':
    REASON,
  'app/(protected)/order-management/customer-groups/components/CustomerGroupsList.tsx':
    REASON,
  'app/(protected)/order-management/customers/components/CustomersList.tsx':
    REASON,
  'app/(protected)/order-management/order-statuses/components/OrderStatusesList.tsx':
    REASON,
  'app/(protected)/order-management/orders/components/OrdersList.tsx': REASON,
  'app/(protected)/project-sales/lead-acceptance/components/AwaitingAcceptanceClient.tsx':
    REASON,
  'app/(protected)/project-sales/order-inquiries/components/OrderInquiriesClient.tsx':
    REASON,
  'app/(protected)/project-sales/order-inquiries/components/OrderInquiryHeadersList.tsx':
    REASON,
  'app/(protected)/project-sales/stock-claims/components/StockClaimsClient.tsx':
    REASON,
  'app/(protected)/resource-management/attachment-directories/components/AttachmentsInFolderPanel.tsx':
    REASON,
  'app/(protected)/resource-management/attachments/components/AttachmentBrowser.tsx':
    REASON,
  'app/(protected)/scm/components/PlanRowDialog.tsx': REASON,
  'app/(protected)/scm/purchase-orders/components/PurchaseOrdersList.tsx':
    REASON,
  'app/(protected)/scm/reorder/components/ReorderResultsGrid.tsx': REASON,
  'app/(protected)/scm/sales-orders/components/SalesOrdersGrid.tsx': REASON,
  'app/(protected)/sla-management/sla-policies/components/SLAPoliciesList.tsx':
    REASON,
  'app/(protected)/system-management/app-store/components/AppStoreAdmin.tsx':
    REASON,
  'app/(protected)/system-management/chat-history/page.tsx': REASON,
  'app/(protected)/system-management/chatbot-domains/components/ChatbotDomainsList.tsx':
    REASON,
  'app/(protected)/system-management/client-errors/page.tsx': REASON,
  'app/(protected)/system-management/companies/components/CompaniesList.tsx':
    REASON,
  'app/(protected)/system-management/import-field-aliases/components/ImportFieldAliasesList.tsx':
    REASON,
  'app/(protected)/system-management/respond-contacts/components/RespondContactsOutboundList.tsx':
    REASON,
  'app/(protected)/system-management/respond-workspaces/components/RespondWorkspacesAdmin.tsx':
    REASON,
  'app/(protected)/user-management/contact-access-agents/components/ContactAccessAgentsGroupedList.tsx':
    REASON,
  'app/(protected)/user-management/users/components/user-list.tsx': REASON,
  'app/(protected)/workflow-forms-management/components/WorkflowSubmissionsList.tsx':
    REASON,
};

describe('R4 / G-1', () => {
  it('every offending file is allowlisted with a reason', () => {
    const offenders = sourceFiles().filter((file) =>
      matches(readStripped(file)),
    );
    const unlisted = offenders.filter((file) => !(file in ALLOWLIST));

    expect(unlisted).toEqual([]);
  });

  it('every allowlist entry still exists and still matches', () => {
    const stale = Object.keys(ALLOWLIST).filter((file) => {
      if (!fs.existsSync(file)) return true;
      return !matches(readStripped(file));
    });

    expect(stale).toEqual([]);
  });
});
