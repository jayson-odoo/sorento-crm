/**
 * D7 / G-1 - no NEW file uses `SheetContent`; the allowlist only shrinks
 *
 * UI v2 phase 0 (UAC G-1, decision D7). The 44 right-side Sheets are retired on desktop in favour of
 * `components/v2/Lightbox.tsx` (a Dialog on desktop, a vaul Drawer at 720 px and below). v1 files still use
 * `SheetContent` and are allowlisted here with the reason "v1, retires per D7 wave"; each wave of the program
 * (phases 2-5) removes its files from the list, and the list reaches zero at sunset (phase 9).
 *
 * The scan is the token `SheetContent` (an import or a use) in any non-test .ts/.tsx under app, components, lib
 * and hooks. `components/ui/sheet.tsx` itself (the definition) is excluded. Comments are stripped first.
 *
 * Same shape as components/ui/raw-table.inventory.test.ts: a source scan, an allowlist of path to reason, and a
 * stale-entry test so the list cannot rot. A new offender fails the first test; a fixed file must leave the
 * allowlist or the second test fails.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ROOTS = ['app', 'components', 'lib', 'hooks'];

const REASON = 'v1, retires per D7 wave';

const PATTERN = /\bSheetContent\b/;
const matches = (src: string) => PATTERN.test(src);
const EXCLUDED_FILES: string[] = ['components/ui/sheet.tsx'];

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

/** Every current file that uses SheetContent, each with a one-line reason. Shrink-only. */
const ALLOWLIST: Record<string, string> = {
  'app/(protected)/complaint-management/complaints/components/ComplaintDetail.tsx':
    REASON,
  'app/(protected)/dealer-kit/tag-templates/components/TemplateVersionsSheet.tsx':
    REASON,
  'app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestDetail.tsx':
    REASON,
  'app/(protected)/procurement-management/stock-inquiries/components/StockInquiryDetail.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/delivery-schedules/components/DeliveryScheduleReviewClient.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/quotation-documents/[documentId]/components/QuotationHistorySheet.tsx':
    REASON,
  'app/(protected)/project-sales/fulfilment-planning/components/FulfilmentPlanningSheet.tsx':
    REASON,
  'app/(protected)/project-sales/fulfilment-planning/components/PlanningHistorySheet.tsx':
    REASON,
  'app/(protected)/resource-management/attachment-directories/components/AttachmentDirectoriesView.tsx':
    REASON,
  'app/(protected)/resource-management/document-access/components/DocumentAccessSheet.tsx':
    REASON,
  'app/(protected)/sales/customer-asks/components/MyCustomerAsksClient.tsx':
    REASON,
  'app/(protected)/scm/reorder/components/PlanExceptionReviewSheet.tsx': REASON,
  'app/(protected)/scm/reorder/components/PlanMethodologySheet.tsx': REASON,
  'app/(protected)/scm/simulation/components/ScenarioDiffSheet.tsx': REASON,
  'app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx':
    REASON,
  'app/(protected)/sla-management/conversation-sla-tracking/components/InterventionTicketDrawer.tsx':
    REASON,
  'app/(protected)/sla-management/conversation-sla-tracking/components/MediaRequestDrawer.tsx':
    REASON,
  'app/(protected)/sla-management/sla-policies/components/SLAPolicyTiersTable.tsx':
    REASON,
  'app/(protected)/store-admin/components/create-shipping-label-sheet/sheet.tsx':
    REASON,
  'app/(protected)/store-admin/components/track-shipping-sheet.tsx': REASON,
  'app/(protected)/store-client/components/sheets/cart-sheet.tsx': REASON,
  'app/(protected)/store-client/components/sheets/filters-sheet.tsx': REASON,
  'app/(protected)/store-client/components/sheets/product-details-sheet.tsx':
    REASON,
  'app/(protected)/store-client/components/sheets/wishlist-sheet.tsx': REASON,
  'app/(protected)/system-management/api-call-logs/components/ApiCallDetailDrawer.tsx':
    REASON,
  'app/(protected)/system-management/chat-history/components/ChatThreadDrawer.tsx':
    REASON,
  'app/(protected)/system-management/chat-history/components/TraceDrawer.tsx':
    REASON,
  'app/(protected)/system-management/chat-history/components/TurnDetailDrawer.tsx':
    REASON,
  'app/(protected)/system-management/client-errors/ClientErrorDetailDrawer.tsx':
    REASON,
  'app/components/layouts/demo10/components/header.tsx': REASON,
  'app/components/layouts/demo3/components/header-logo.tsx': REASON,
  'app/components/layouts/demo4/components/header.tsx': REASON,
  'app/components/layouts/demo5/components/header-logo.tsx': REASON,
  'app/components/layouts/demo6/components/header.tsx': REASON,
  'app/components/layouts/demo7/components/header-logo.tsx': REASON,
  'app/components/layouts/demo8/components/header.tsx': REASON,
  'app/components/layouts/demo9/components/header-logo.tsx': REASON,
  'app/components/partials/topbar/chat-sheet.tsx': REASON,
  'app/components/partials/topbar/dropdown-menu-notifications.tsx': REASON,
  'app/components/partials/topbar/notifications-sheet.tsx': REASON,
  'app/components/partials/topbar/sheet-chat.tsx': REASON,
  'components/common/ActivitiesNotesPanel/index.tsx': REASON,
  'components/dealer-kit/RequestVersionsSheet.tsx': REASON,
  'components/my-downloads/MyDownloadsDrawer.tsx': REASON,
  'components/upload-activity/UploadActivityDrawer.tsx': REASON,
};

describe('D7 / G-1', () => {
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
