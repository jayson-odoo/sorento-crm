/**
 * S4-03 / D3 - a row opens its record, and a log row opens nothing.
 *
 * S1 gave the grid `rowHref` (a real link target on the `<tr>`, carrying the
 * list's page/sort/filter state) and kept `onRowClick` for the lists whose
 * record is edited in a lightbox. S3 wired 24 of the 26 lists the audit found
 * with a detail route and no row click. S4 finishes the set and states, in one
 * place, which lists are deliberately inert.
 *
 * Why a source scan: `rowHref` is a PROP, and the thing worth guarding is that
 * a named list still passes one. Rendering these lists would mean standing up
 * their query hooks, their permission gates and their toolbars to assert a
 * single prop, and it would say nothing about the list that quietly drops it
 * next month. The inert half matters just as much - D3 says a log or sub-table
 * carries no pointer cursor, and the grid only draws one when a row prop is
 * present, so "neither prop" IS the assertion.
 */
import fs from 'node:fs';
import { describe, it, expect } from 'vitest';

/** Lists that navigate to a detail route. */
const ROW_HREF = [
  'app/(protected)/marketing-management/campaigns/components/CampaignsList.tsx',
  'app/(protected)/master-data-management/units-of-measure/components/UOMList.tsx',
  // Brands moved out of ROW_LIGHTBOX in the S5 fix round: `/brands/[id]` existed
  // but nothing linked to it, so the row opened an edit lightbox and the record
  // page could only be typed. The record now reads and edits in one layout, and
  // the row opens it; Add is still a lightbox.
  'app/(protected)/master-data-management/brands/components/BrandsList.tsx',
];

/**
 * Lists whose record has no detail page and is edited in a lightbox: the row
 * click opens that lightbox instead (D3, second clause).
 */
const ROW_LIGHTBOX = [
  'app/(protected)/user-management/access-agents/components/ContactAccessAgentsTable.tsx',
  'app/(protected)/user-management/contacts/[id]/components/ContactAccessAgentsTable.tsx',
  // Audit Logs looks like a log table and is not one: a row opens an "Audit
  // entry details" lightbox holding the before and after values, which is the
  // record's only view. Reported during the S4 sweep as a pointer that does
  // nothing; it was the missing guard on the onRowClick branch, not a stray
  // cursor. Verified on the lane: the dialog opens and is titled.
  'app/(protected)/system-management/audit-logs/components/AuditLogsList.tsx',
];

/**
 * Log tables and sub-tables. A row here is an event, a tier or a line, not a
 * record with a page of its own, so clicking it has nowhere to go and a pointer
 * cursor would be a promise the screen cannot keep.
 *
 * "It is a log" is not the test - having somewhere to go is. Audit Logs is in
 * ROW_LIGHTBOX above for exactly that reason.
 */
const INERT = [
  'app/(protected)/sla-management/conversation-sla-tracking/components/EventLogTable.tsx',
  'app/(protected)/sla-management/escalation-logs/components/EventLogList.tsx',
  'app/(protected)/sla-management/sla-policies/components/SLAPolicyTiersTable.tsx',
  'app/(protected)/system-management/scheduled-tasks/components/RunLogsTable.tsx',
  'app/(protected)/system-management/automation/components/AutomationRunsTable.tsx',
  'app/(protected)/inventory-management/stock-ledger/components/StockLedgerList.tsx',
  'app/(protected)/user-management/logs/components/log-list.tsx',
];

describe('Row opens the record (S4-03)', () => {
  it('S4-03: the lists with a detail route pass rowHref', () => {
    for (const file of ROW_HREF) {
      const src = fs.readFileSync(file, 'utf8');
      expect(src, file).toContain('rowHref');
    }
  });

  it('S4-03: the lightbox lists open their editor from the row', () => {
    for (const file of ROW_LIGHTBOX) {
      const src = fs.readFileSync(file, 'utf8');
      expect(src, file).toContain('onRowClick');
    }
  });

  it('S4-03: log and sub-tables carry neither prop', () => {
    for (const file of INERT) {
      const src = fs.readFileSync(file, 'utf8');
      expect(src.includes('rowHref'), `${file} passes rowHref`).toBe(false);
      expect(src.includes('onRowClick'), `${file} passes onRowClick`).toBe(false);
    }
  });
});
