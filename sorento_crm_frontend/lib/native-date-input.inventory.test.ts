/**
 * R1 / G-1 - no NEW native date input; the allowlist only shrinks
 *
 * UI v2 phase 0 (UAC G-1, rule R1). Every date is dd/mm/yyyy through `lib/format/date.ts`; a native
 * `<input type="date">` or `type="datetime-local"` renders in the browser locale and cannot honour that. v1 files
 * that still use one are allowlisted with the reason "v1, retires per R1 wave".
 *
 * The scan is the JSX attribute `type="date"`, `type='date'` or `type={'date'}` (and `datetime-local`) in any
 * non-test .ts/.tsx under app, components, lib and hooks. Comments are stripped first. A field-definition object
 * such as `{ key: 'created_at', type: 'date' }` is data, not an input, and does not match.
 *
 * Same shape as components/ui/raw-table.inventory.test.ts: a source scan, an allowlist of path to reason, and a
 * stale-entry test so the list cannot rot. A new offender fails the first test; a fixed file must leave the
 * allowlist or the second test fails.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ROOTS = ['app', 'components', 'lib', 'hooks'];

const REASON = 'v1, retires per R1 wave';

const PATTERN = /\btype=(?:"|'|\{\s*["'`])(?:date|datetime-local)\b/;
const matches = (src: string) => PATTERN.test(src);
const EXCLUDED_FILES: string[] = [];

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

/** Every current file that renders a native date input, each with a one-line reason. Shrink-only. */
const ALLOWLIST: Record<string, string> = {
  'app/(auth)/portal/components/LandingToolbar.tsx': REASON,
  'app/(auth)/portal/sales_opportunity/components/SalesOpportunityPortalDetail.tsx':
    REASON,
  'app/(auth)/portal/sales_opportunity/components/SalesOpportunityPortalForm.tsx':
    REASON,
  'app/(protected)/account/notifications/components/coverage-manager.tsx':
    REASON,
  'app/(protected)/account/notifications/components/coverage-section.tsx':
    REASON,
  'app/(protected)/complaint-management/complaints/components/ComplaintForm.tsx':
    REASON,
  'app/(protected)/integration-management/integration-logs/components/IntegrationLogsList.tsx':
    REASON,
  'app/(protected)/marketing-management/campaigns/components/CampaignForm.tsx':
    REASON,
  'app/(protected)/marketing-management/promotions/components/PromotionForm.tsx':
    REASON,
  'app/(protected)/master-data-management/certificates/components/CertificateFormDialog.tsx':
    REASON,
  'app/(protected)/order-management/orders/components/OrderForm.tsx': REASON,
  'app/(protected)/procurement-management/grn/components/GRNForm.tsx': REASON,
  'app/(protected)/procurement-management/packing-lists/components/PackingListDetailsTab.tsx':
    REASON,
  'app/(protected)/procurement-management/packing-lists/components/PackingListForm.tsx':
    REASON,
  'app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestForm.tsx':
    REASON,
  'app/(protected)/procurement-management/spo-allocations/components/SPODocumentDetail.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/components/PurchaseOrderDialog.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/components/PurchaseOrderHeaderCard.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/components/TaskFormDialog.tsx':
    REASON,
  'app/(protected)/project-sales/_shared/components/AutoLinkOrderInquiryDialog.tsx':
    REASON,
  'app/(protected)/project-sales/_shared/components/ProjectForm.tsx': REASON,
  'app/(protected)/project-sales/order-inquiries/components/OrderInquiriesClient.tsx':
    REASON,
  'app/(protected)/project-sales/sample-requests/components/SampleRequestDetail.tsx':
    REASON,
  'app/(protected)/resource-management/attachments/components/AttachmentBrowser.tsx':
    REASON,
  'app/(protected)/sales/opportunities/[id]/components/SalesOpportunityDetail.tsx':
    REASON,
  'app/(protected)/sales/opportunities/components/SalesOpportunityModal.tsx':
    REASON,
  'app/(protected)/sales/teams/[id]/components/SalesTeamDetail.tsx': REASON,
  'app/(protected)/sales/teams/components/SalesTeamModal.tsx': REASON,
  'app/(protected)/scm/loading-plan/components/LoadingPlanView.tsx': REASON,
  'app/(protected)/scm/loading-plan/components/PlanContainerDialog.tsx': REASON,
  'app/(protected)/scm/policies/components/CurrencyRatesPanel.tsx': REASON,
  'app/(protected)/scm/policies/components/FulfilmentPriorityPanel.tsx': REASON,
  'app/(protected)/scm/purchase-orders/[id]/components/PurchaseOrderDetail.tsx':
    REASON,
  'app/(protected)/scm/reorder/components/PlanHeaderTab.tsx': REASON,
  'app/(protected)/scm/reorder/components/RunPlanningModal.tsx': REASON,
  'app/(protected)/scm/sales-orders/[id]/components/SalesOrderDetail.tsx':
    REASON,
  'app/(protected)/scm/sales-orders/components/SalesOrderFormModal.tsx': REASON,
  'app/(protected)/sla-management/_shared/FormSLATrackerDetail.tsx': REASON,
  'app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx':
    REASON,
  'app/(protected)/sla-management/conversation-sla-tracking/components/ExtendDueDialog.tsx':
    REASON,
  'app/(protected)/system-management/activity/components/ActivityTimeline.tsx':
    REASON,
  'app/(protected)/system-management/api-call-logs/page.tsx': REASON,
  'app/(protected)/system-management/audit-logs/components/AuditLogsList.tsx':
    REASON,
  'app/(protected)/system-management/client-errors/page.tsx': REASON,
  'app/(protected)/system-management/health/components/HealthDashboard.tsx':
    REASON,
  'app/(protected)/system-management/scheduled-tasks/components/ScheduledTaskForm.tsx':
    REASON,
  'app/(protected)/system-management/work-calendar/components/PublicHolidayFormDialog.tsx':
    REASON,
  'app/(protected)/ticket-management/tickets/new/page.tsx': REASON,
  'app/(protected)/user-management/access-agents/components/ContactAgentAccessDialog.tsx':
    REASON,
  'app/(protected)/workflow-forms-management/components/WorkflowDynamicFields.tsx':
    REASON,
  'components/common/NewProductApplicationHeader.tsx': REASON,
  'components/ideas/IdeasListView.tsx': REASON,
};

describe('R1 / G-1', () => {
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
