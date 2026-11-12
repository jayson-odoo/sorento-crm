/**
 * DATE-PICKER-UNIFY guard (AC5, AC7): a UTC API timestamp is shown in Malaysia time.
 *
 * `formatDateTime` / `formatDate` from `lib/helpers` format in the browser timezone; the API sends
 * UTC, so these screens must use `formatDateTimeInMalaysia` / `formatDateInMalaysia`.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const root = path.resolve(__dirname, '..');

const UTC_DISPLAY_FILES = [
  'app/(protected)/sla-management/sla-policies/components/SLAPolicyDetail.tsx',
  'app/(protected)/sla-management/form-sla-tracking/components/FormSLATrackingList.tsx',
  'app/(protected)/sla-management/team-pending/components/TeamPendingList.tsx',
  'app/(protected)/sla-management/kpi-dashboard/SLAKpiDashboardContent.tsx',
  'app/(protected)/sla-management/conversation-sla-tracking/components/EventLogTable.tsx',
  'app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx',
  'app/(protected)/sla-management/conversation-sla-tracking/components/ExtendDueDialog.tsx',
  'app/(protected)/sla-management/conversation-sla-tracking/components/SLATrackingDashboard.tsx',
  'app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingList.tsx',
  'app/(protected)/sla-management/escalation-logs/components/EventLogList.tsx',
  'app/(protected)/sla-management/_shared/SlaExtensionBanner.tsx',
  'app/(protected)/sla-management/_shared/FormSLATrackingTab.tsx',
  'app/(protected)/sla-management/_shared/FormSLATrackerDetail.tsx',
  'app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestDetail.tsx',
];

describe('DATE-PICKER-UNIFY: UTC timestamps render in Malaysia time', () => {
  it('lists files that exist', () => {
    for (const file of UTC_DISPLAY_FILES) {
      expect(fs.existsSync(path.join(root, file)), file).toBe(true);
    }
  });

  it('none of them calls the browser-timezone formatDateTime( or formatDate( helper', () => {
    const offenders: string[] = [];
    for (const file of UTC_DISPLAY_FILES) {
      const lines = fs.readFileSync(path.join(root, file), 'utf8').split('\n');
      lines.forEach((text, i) => {
        if (text.trim().startsWith('//') || text.trim().startsWith('*')) return;
        if (/\b(formatDateTime|formatDate)\(/.test(text)) offenders.push(`${file}:${i + 1}`);
      });
    }
    expect(offenders).toEqual([]);
  });
});
