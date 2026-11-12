/**
 * DATE-PICKER-UNIFY guard (AC8): no native date input outside the allowlist.
 *
 * A date field is the shared typeable `DatePicker` / `DatePickerField` / `DateRangePicker`,
 * never a browser `type="date"` or `type="datetime-local"` (it renders in the browser locale and
 * shifts the day through timezones). Each slice migrates files and removes them from ALLOWED;
 * the last slice leaves it empty.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const root = path.resolve(__dirname, '..');

const PENDING = [
  'app/(auth)/portal/components/LandingToolbar.tsx',
  'app/(auth)/portal/components/SampleRequestForm.tsx',
  'app/(auth)/portal/components/SubmissionForm.tsx',
  'app/(auth)/portal/sales_opportunity/components/SalesOpportunityPortalDetail.tsx',
  'app/(auth)/portal/sales_opportunity/components/SalesOpportunityPortalForm.tsx',
  'app/(protected)/account/notifications/components/coverage-manager.tsx',
  'app/(protected)/account/notifications/components/coverage-section.tsx',
  'app/(protected)/complaint-management/complaints/components/ComplaintForm.tsx',
  'app/(protected)/integration-management/integration-logs/components/IntegrationLogsList.tsx',
  'app/(protected)/marketing-management/campaigns/components/CampaignForm.tsx',
  'app/(protected)/marketing-management/promotions/components/PromotionForm.tsx',
  'app/(protected)/master-data-management/certificates/components/CertificateFormDialog.tsx',
  'app/(protected)/order-management/orders/components/OrderForm.tsx',
  'app/(protected)/procurement-management/grn/components/GRNForm.tsx',
  'app/(protected)/procurement-management/packing-lists/components/PackingListDetailsTab.tsx',
  'app/(protected)/procurement-management/packing-lists/components/PackingListForm.tsx',
  'app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestForm.tsx',
  'app/(protected)/procurement-management/spo-allocations/components/SPODocumentDetail.tsx',
  'app/(protected)/project-sales/[projectId]/components/PurchaseOrderDialog.tsx',
  'app/(protected)/project-sales/[projectId]/components/PurchaseOrderHeaderCard.tsx',
  'app/(protected)/project-sales/[projectId]/components/TaskFormDialog.tsx',
  'app/(protected)/project-sales/_shared/components/AutoLinkOrderInquiryDialog.tsx',
  'app/(protected)/project-sales/_shared/components/ProjectForm.tsx',
  'app/(protected)/project-sales/order-inquiries/components/OrderInquiriesClient.tsx',
  'app/(protected)/project-sales/sample-requests/components/SampleRequestDetail.tsx',
  'app/(protected)/project-sales/sample-requests/components/SampleRequestForm.tsx',
  'app/(protected)/resource-management/attachments/components/AttachmentBrowser.tsx',
  'app/(protected)/sales/opportunities/[id]/components/SalesOpportunityDetail.tsx',
  'app/(protected)/sales/opportunities/components/SalesOpportunityModal.tsx',
  'app/(protected)/sales/teams/[id]/components/SalesTeamDetail.tsx',
  'app/(protected)/sales/teams/components/SalesTeamModal.tsx',
  'app/(protected)/scm/loading-plan/components/LoadingPlanView.tsx',
  'app/(protected)/scm/loading-plan/components/PlanContainerDialog.tsx',
  'app/(protected)/scm/policies/components/CurrencyRatesPanel.tsx',
  'app/(protected)/scm/policies/components/FulfilmentPriorityPanel.tsx',
  'app/(protected)/scm/purchase-orders/[id]/components/PurchaseOrderDetail.tsx',
  'app/(protected)/scm/reorder/components/PlanHeaderTab.tsx',
  'app/(protected)/scm/reorder/components/RunPlanningModal.tsx',
  'app/(protected)/scm/sales-orders/[id]/components/SalesOrderDetail.tsx',
  'app/(protected)/scm/sales-orders/components/SalesOrderFormModal.tsx',
  'app/(protected)/sla-management/_shared/FormSLATrackerDetail.tsx',
  'app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx',
  'app/(protected)/sla-management/conversation-sla-tracking/components/ExtendDueDialog.tsx',
  'app/(protected)/system-management/activity/components/ActivityTimeline.tsx',
  'app/(protected)/system-management/api-call-logs/page.tsx',
  'app/(protected)/system-management/audit-logs/components/AuditLogsList.tsx',
  'app/(protected)/system-management/client-errors/page.tsx',
  'app/(protected)/system-management/health/components/HealthDashboard.tsx',
  'app/(protected)/system-management/scheduled-tasks/components/ScheduledTaskForm.tsx',
  'app/(protected)/system-management/work-calendar/components/PublicHolidayFormDialog.tsx',
  'app/(protected)/ticket-management/tickets/new/page.tsx',
  'app/(protected)/user-management/access-agents/components/ContactAgentAccessDialog.tsx',
  'app/(protected)/workflow-forms-management/components/WorkflowDynamicFields.tsx',
  'components/common/NewProductApplicationHeader.tsx',
  'components/ideas/IdeasListView.tsx',
  'components/list/ListQueryFilterDialog.tsx',
  'components/rule-builder/RuleBuilder.tsx',
];

/** file -> why it may still hold a native date input. */
export const ALLOWED: Record<string, string> = Object.fromEntries(
  PENDING.map((file) => [file, 'native date input, migrates in a later DATE-PICKER-UNIFY slice']),
);

const NATIVE_PATTERNS: RegExp[] = [
  /type=["']date["']/,
  /type=["']datetime-local["']/,
  /type=\{[^}]*['"](date|datetime-local)['"]/,
  /\?\s*['"](date|datetime-local)['"]\s*:/,
  /['"]date['"]\s*\?\s*['"](date|datetime-local)['"]/,
];

const SKIP_PATHS = [
  /^app\/components\/layouts\/demo/,
  /^app\/\(protected\)\/components\/demo/,
  /^app\/\(protected\)\/store-admin\//,
  /^app\/\(protected\)\/public-profile\//,
  /^app\/\(protected\)\/account\/home\//,
];

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    const abs = path.join(root, dir);
    if (!fs.existsSync(abs)) return;
    for (const entry of fs.readdirSync(abs, { withFileTypes: true })) {
      const rel = path.posix.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(rel);
      } else if (/\.tsx?$/.test(entry.name) && !/\.(test|spec)\.tsx?$/.test(entry.name)) {
        if (!SKIP_PATHS.some((re) => re.test(rel))) out.push(rel);
      }
    }
  };
  for (const dir of ['app', 'components', 'lib', 'hooks', 'services']) walk(dir);
  return out;
}

/** Lines that are code, not comments. */
function codeLines(src: string): { line: number; text: string }[] {
  const out: { line: number; text: string }[] = [];
  let inBlock = false;
  src.split('\n').forEach((raw, i) => {
    let text = raw;
    if (inBlock) {
      const end = text.indexOf('*/');
      if (end === -1) return;
      text = text.slice(end + 2);
      inBlock = false;
    }
    text = text.replace(/\/\*.*?\*\//g, '');
    const open = text.indexOf('/*');
    if (open !== -1) {
      text = text.slice(0, open);
      inBlock = true;
    }
    if (text.trim().startsWith('//')) return;
    out.push({ line: i + 1, text: text.replace(/\s\/\/.*$/, '') });
  });
  return out;
}

function nativeLines(file: string): number[] {
  const src = fs.readFileSync(path.join(root, file), 'utf8');
  return codeLines(src)
    .filter(({ text }) => NATIVE_PATTERNS.some((re) => re.test(text)))
    .map(({ line }) => line);
}

describe('DATE-PICKER-UNIFY: no native date input outside the allowlist', () => {
  it('no source file outside ALLOWED holds a native date input', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (ALLOWED[file]) continue;
      for (const line of nativeLines(file)) offenders.push(`${file}:${line}`);
    }
    expect(offenders).toEqual([]);
  });

  it('every ALLOWED file exists and still holds a native input (a migrated file must leave the list)', () => {
    const stale: string[] = [];
    for (const file of Object.keys(ALLOWED)) {
      if (!fs.existsSync(path.join(root, file)) || nativeLines(file).length === 0) stale.push(file);
    }
    expect(stale).toEqual([]);
  });
});
