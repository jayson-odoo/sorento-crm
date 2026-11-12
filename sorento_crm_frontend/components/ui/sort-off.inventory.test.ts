/**
 * R3 / G-1 - no NEW `enableSorting: false` column; the allowlist only shrinks
 *
 * UI v2 phase 0 (UAC G-1, rule R3). Every column is sortable server-side in v2. A column definition with
 * `enableSorting: false` opts out, so the files that still do are allowlisted with the reason "v1, retires per R3
 * wave" and the list only shrinks.
 *
 * The scan is the literal `enableSorting: false` in any non-test .ts/.tsx under app, components, lib and hooks.
 * Comments are stripped first. The unit is the FILE, so a second opt-out inside an already-listed file is not
 * caught; the wave that clears a file removes all of them.
 *
 * Same shape as components/ui/raw-table.inventory.test.ts: a source scan, an allowlist of path to reason, and a
 * stale-entry test so the list cannot rot. A new offender fails the first test; a fixed file must leave the
 * allowlist or the second test fails.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ROOTS = ['app', 'components', 'lib', 'hooks'];

const REASON = 'v1, retires per R3 wave';

const PATTERN = /\benableSorting:\s*false\b/;
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

/** Every current file that has a column with enableSorting: false, each with a one-line reason. Shrink-only. */
const ALLOWLIST: Record<string, string> = {
  'app/(protected)/account/api-keys/components/api-integrations.tsx': REASON,
  'app/(protected)/account/appearance/components/api-integrations.tsx': REASON,
  'app/(protected)/account/billing/history/components/invoicing.tsx': REASON,
  'app/(protected)/account/invite-a-friend/components/invites.tsx': REASON,
  'app/(protected)/account/members/permissions-toggle/components/members.tsx':
    REASON,
  'app/(protected)/account/members/team-info/components/members.tsx': REASON,
  'app/(protected)/account/members/team-members/components/members.tsx': REASON,
  'app/(protected)/account/members/teams/components/teams.tsx': REASON,
  'app/(protected)/account/security/allowed-ip-addresses/components/ip-addresses.tsx':
    REASON,
  'app/(protected)/account/security/backup-and-recovery/components/backup.tsx':
    REASON,
  'app/(protected)/account/security/device-management/components/device.tsx':
    REASON,
  'app/(protected)/account/security/security-log/components/security-log.tsx':
    REASON,
  'app/(protected)/complaint-management/_shared/LinkedComplaintsPanel.tsx':
    REASON,
  'app/(protected)/complaint-management/complaint-resolutions/components/ComplaintResolutionsList.tsx':
    REASON,
  'app/(protected)/complaint-management/complaint-root-causes/components/ComplaintRootCausesList.tsx':
    REASON,
  'app/(protected)/complaint-management/complaints/components/ComplaintsList.tsx':
    REASON,
  'app/(protected)/components/demo1/light-sidebar/components/teams.tsx': REASON,
  'app/(protected)/dealer-kit/accessory-templates/components/AccessoryTemplatesList.tsx':
    REASON,
  'app/(protected)/dealer-kit/brochure-images/components/BrochureImagePicker.tsx':
    REASON,
  'app/(protected)/dealer-kit/tag-templates/components/TagTemplatesList.tsx':
    REASON,
  'app/(protected)/integration-management/whatsapp-templates/components/TemplatesGrid.tsx':
    REASON,
  'app/(protected)/inventory-management/stock-transfers/components/StockTransfersPanel.tsx':
    REASON,
  'app/(protected)/marketing-management/promotions/components/PromotionsList.tsx':
    REASON,
  'app/(protected)/master-data-management/accessories/components/AccessoryColumns.tsx':
    REASON,
  'app/(protected)/master-data-management/brands/components/BrandTable.tsx':
    REASON,
  'app/(protected)/master-data-management/certificates/components/CertificateCoveredProducts.tsx':
    REASON,
  'app/(protected)/master-data-management/certificates/components/CertificatesList.tsx':
    REASON,
  'app/(protected)/master-data-management/costing/components/CostingView.tsx':
    REASON,
  'app/(protected)/master-data-management/flyer-spec-proposals/components/FlyerSpecBatchesList.tsx':
    REASON,
  'app/(protected)/master-data-management/item-classes/components/ItemClassList.tsx':
    REASON,
  'app/(protected)/master-data-management/lookup-sets/components/LookupSetsList.tsx':
    REASON,
  'app/(protected)/master-data-management/product-sets/components/ProductSetsList.tsx':
    REASON,
  'app/(protected)/master-data-management/product-specifications/components/SpecRegistryGrid.tsx':
    REASON,
  'app/(protected)/master-data-management/product-specifications/components/SpecRulesGrid.tsx':
    REASON,
  'app/(protected)/master-data-management/product-specifications/components/TryInChatbotDialog.tsx':
    REASON,
  'app/(protected)/master-data-management/product-specifications/components/WordsDataGrid.tsx':
    REASON,
  'app/(protected)/master-data-management/product-specifications/components/record/ValuesAndWordsTab.tsx':
    REASON,
  'app/(protected)/master-data-management/products/catalogue-photos/[id]/components/CataloguePhotosGrid.tsx':
    REASON,
  'app/(protected)/master-data-management/products/components/BarcodeImportDialog.tsx':
    REASON,
  'app/(protected)/master-data-management/products/components/ProductsList.tsx':
    REASON,
  'app/(protected)/master-data-management/sales-agents/[id]/components/SalesAgentClassTab.tsx':
    REASON,
  'app/(protected)/master-data-management/sales-agents/[id]/components/SalesAgentCustomersTab.tsx':
    REASON,
  'app/(protected)/master-data-management/spec-verification/components/SpecVerificationList.tsx':
    REASON,
  'app/(protected)/network/user-table/app-roster/components/users.tsx': REASON,
  'app/(protected)/network/user-table/market-authors/components/users.tsx':
    REASON,
  'app/(protected)/network/user-table/saas-users/components/users.tsx': REASON,
  'app/(protected)/network/user-table/store-clients/components/store-clients.tsx':
    REASON,
  'app/(protected)/network/user-table/team-crew/components/users.tsx': REASON,
  'app/(protected)/network/user-table/visitors/components/visitors.tsx': REASON,
  'app/(protected)/order-management/branches/components/BranchesList.tsx':
    REASON,
  'app/(protected)/order-management/customer-groups/[id]/components/CustomerGroupDetail.tsx':
    REASON,
  'app/(protected)/order-management/customer-groups/components/CustomerGroupsList.tsx':
    REASON,
  'app/(protected)/order-management/customers/components/CustomerGroupLedgersCard.tsx':
    REASON,
  'app/(protected)/order-management/customers/components/CustomersList.tsx':
    REASON,
  'app/(protected)/order-management/orders/components/OrdersList.tsx': REASON,
  'app/(protected)/procurement-management/cost-price-uploads/[id]/components/CostPriceLinesTab.tsx':
    REASON,
  'app/(protected)/procurement-management/grn/components/GRNList.tsx': REASON,
  'app/(protected)/procurement-management/packing-lists/components/PackingListLinesTab.tsx':
    REASON,
  'app/(protected)/procurement-management/packing-lists/components/PackingListsList.tsx':
    REASON,
  'app/(protected)/procurement-management/packing-lists/components/SpoPlannerTable.tsx':
    REASON,
  'app/(protected)/procurement-management/spo-allocations/components/SPODocumentDetail.tsx':
    REASON,
  'app/(protected)/procurement-management/suppliers/[id]/components/SupplierPricesTab.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/components/POLinesProgressGrid.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/components/ProjectAccessPanel.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/components/QuotationLinesGrid.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/components/QuotationsPanel.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/order-inquiries/components/OrderInquiryClient.tsx':
    REASON,
  'app/(protected)/project-sales/[projectId]/quotation-documents/[documentId]/components/QuotationSpecSheetsList.tsx':
    REASON,
  'app/(protected)/project-sales/_shared/components/LinkDocumentDialog.tsx':
    REASON,
  'app/(protected)/project-sales/_shared/components/RequestReserveDialog.tsx':
    REASON,
  'app/(protected)/project-sales/fulfilment-planning/components/BoardCellBreakdownDialog.tsx':
    REASON,
  'app/(protected)/project-sales/fulfilment-planning/components/BoardTransfersPanel.tsx':
    REASON,
  'app/(protected)/project-sales/fulfilment-planning/components/FulfilmentPlanningClient.tsx':
    REASON,
  'app/(protected)/project-sales/fulfilment-planning/components/PileQueueDialog.tsx':
    REASON,
  'app/(protected)/project-sales/lead-acceptance/components/AwaitingAcceptanceClient.tsx':
    REASON,
  'app/(protected)/project-sales/leads/components/LeadsGrid.tsx': REASON,
  'app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryLineHistoryDialog.tsx':
    REASON,
  'app/(protected)/project-sales/order-inquiries/[id]/components/ReserveConfirmDialog.tsx':
    REASON,
  'app/(protected)/project-sales/order-inquiries/[id]/components/orderInquiryHeaderLinesColumns.tsx':
    REASON,
  'app/(protected)/project-sales/order-inquiries/components/OrderInquiryHeadersList.tsx':
    REASON,
  'app/(protected)/project-sales/order-inquiries/components/orderInquiryWorklistColumns.tsx':
    REASON,
  'app/(protected)/project-sales/parties/[partyId]/components/PartyContactsPanel.tsx':
    REASON,
  'app/(protected)/project-sales/parties/components/PartiesClient.tsx': REASON,
  'app/(protected)/project-sales/planning-changes/components/PlanningChangesListClient.tsx':
    REASON,
  'app/(protected)/project-sales/plans/components/PlansClient.tsx': REASON,
  'app/(protected)/project-sales/quotation-templates/components/QuotationTemplatesClient.tsx':
    REASON,
  'app/(protected)/project-sales/setup/components/ProjectSetupClient.tsx':
    REASON,
  'app/(protected)/project-sales/stock-debt/components/SnapshotClient.tsx':
    REASON,
  'app/(protected)/project-sales/stock-debt/components/SnapshotsList.tsx':
    REASON,
  'app/(protected)/project-sales/stock-debt/components/StockDebtClient.tsx':
    REASON,
  'app/(protected)/resource-management/attachment-directories/components/AttachmentsInFolderPanel.tsx':
    REASON,
  'app/(protected)/resource-management/attachments/components/AttachmentBrowser.tsx':
    REASON,
  'app/(protected)/sales/set-apart-customers/components/SetApartView.tsx':
    REASON,
  'app/(protected)/sales/targets/components/SalesTargetsView.tsx': REASON,
  'app/(protected)/sales/teams/components/SalesTeamsView.tsx': REASON,
  'app/(protected)/scm/components/PlanRowDialog.tsx': REASON,
  'app/(protected)/scm/components/ProductPerspectiveGrid.tsx': REASON,
  'app/(protected)/scm/consignments/components/ConsignmentsList.tsx': REASON,
  'app/(protected)/scm/loading-plan/components/ContainerRequestSection.tsx':
    REASON,
  'app/(protected)/scm/loading-plan/components/LoadingPlansGrid.tsx': REASON,
  'app/(protected)/scm/market/components/MarketTopicsGrid.tsx': REASON,
  'app/(protected)/scm/policies/components/ReorderPolicyGrid.tsx': REASON,
  'app/(protected)/scm/proforma-invoices/[id]/components/ProformaInvoiceDetail.tsx':
    REASON,
  'app/(protected)/scm/proforma-invoices/[id]/components/ProformaInvoicePackingTab.tsx':
    REASON,
  'app/(protected)/scm/proforma-invoices/components/ConvertToPackingListDialog.tsx':
    REASON,
  'app/(protected)/scm/proforma-invoices/components/ProformaInvoicesView.tsx':
    REASON,
  'app/(protected)/scm/purchase-orders/components/PurchaseOrdersList.tsx':
    REASON,
  'app/(protected)/scm/reorder/components/CoverageTimelinePanel.tsx': REASON,
  'app/(protected)/scm/reorder/components/CoveredByStockView.tsx': REASON,
  'app/(protected)/scm/reorder/components/NeedsLevelView.tsx': REASON,
  'app/(protected)/scm/reorder/components/PlanLinesGrid.tsx': REASON,
  'app/(protected)/scm/reorder/components/PoWorklistView.tsx': REASON,
  'app/(protected)/scm/reorder/components/ReorderRunsGrid.tsx': REASON,
  'app/(protected)/scm/sales-orders/[id]/components/SalesOrderDetail.tsx':
    REASON,
  'app/(protected)/scm/sales-orders/components/SalesOrdersGrid.tsx': REASON,
  'app/(protected)/scm/simulation/components/ScenariosGrid.tsx': REASON,
  'app/(protected)/sla-management/message-snippets/components/MessageSnippetsList.tsx':
    REASON,
  'app/(protected)/store-admin/dashboard/components/recent-orders.tsx': REASON,
  'app/(protected)/store-admin/inventory/all-products/components/all-planning.tsx':
    REASON,
  'app/(protected)/system-management/ai-assistant/prompts/components/PromptDetail.tsx':
    REASON,
  'app/(protected)/system-management/app-store/components/AppStoreAdmin.tsx':
    REASON,
  'app/(protected)/system-management/chat-history/page.tsx': REASON,
  'app/(protected)/system-management/client-errors/page.tsx': REASON,
  'app/(protected)/system-management/companies/components/CompanyTable.tsx':
    REASON,
  'app/(protected)/system-management/import-field-aliases/components/ImportFieldAliasesList.tsx':
    REASON,
  'app/(protected)/system-management/import-jobs/autocount-pull/components/CompareMappingDialog.tsx':
    REASON,
  'app/(protected)/system-management/respond-contacts/components/RespondContactsOutboundList.tsx':
    REASON,
  'app/(protected)/system-management/respond-workspaces/components/RespondWorkspacesAdmin.tsx':
    REASON,
  'app/(protected)/system-management/topic-audit/components/TopicAuditScreen.tsx':
    REASON,
  'app/(protected)/system-management/translations/components/TranslationsList.tsx':
    REASON,
  'app/(protected)/ticket-management/tickets/components/TicketsList.tsx':
    REASON,
  'app/(protected)/user-management/account/logs/components/log-list.tsx':
    REASON,
  'app/(protected)/user-management/contact-access-agents/components/ContactAccessAgentsList.tsx':
    REASON,
  'app/(protected)/user-management/contact-access-types/components/ContactAccessTypesAdmin.tsx':
    REASON,
  'app/(protected)/user-management/contact-tags/components/ContactTagsAdmin.tsx':
    REASON,
  'app/(protected)/user-management/contacts/[id]/components/ContactChatbotSection.tsx':
    REASON,
  'app/(protected)/user-management/logs/components/log-list.tsx': REASON,
  'app/(protected)/user-management/market-segments/components/MarketSegmentsAdmin.tsx':
    REASON,
  'app/(protected)/user-management/onboarding-requests/components/OnboardingRequestList.tsx':
    REASON,
  'app/(protected)/user-management/permissions/components/permission-list.tsx':
    REASON,
  'app/(protected)/user-management/roles/components/role-list.tsx': REASON,
  'app/(protected)/user-management/settings/portal-revisions/page.tsx': REASON,
  'app/(protected)/user-management/users/[id]/logs/components/log-list.tsx':
    REASON,
  'app/(protected)/user-management/users/components/user-list.tsx': REASON,
  'app/(protected)/workflow-forms-management/components/WorkflowDefinitionsList.tsx':
    REASON,
  'app/(protected)/workflow-forms-management/components/WorkflowSubmissionsList.tsx':
    REASON,
  'components/common/PanelDataGrid.tsx': REASON,
  'components/common/onboarding/PeopleGrid.tsx': REASON,
  'components/ideas/IdeasListView.tsx': REASON,
  'components/spec-proposals/SpecProposalReview.tsx': REASON,
  'components/spec-table/SpecTable.tsx': REASON,
  'components/ui/data-grid-select-column.tsx': REASON,
};

describe('R3 / G-1', () => {
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
