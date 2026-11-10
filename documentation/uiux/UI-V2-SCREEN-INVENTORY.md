# UI v2: screen inventory

Generated 11 Nov 2026 from `main` at `6e6657e2` by walking every `sorento_crm_frontend/app/(protected)/**/page.tsx`
(469 pages). The archetype is a first-pass classification from the route shape and page source; the discovery
round (`UI-V2-DISCOVERY.md`) corrects it where a page was opened. Rules, in order:

1. `demo (retire)`: Metronic demo areas (`account`, `public-profile`, `network`, `store-client`, `store-admin`,
   `dark-sidebar`, `i18n-test`, `connect`).
2. `redirect`: a short page whose body is `redirect(...)`.
3. `form`: route ends in `/new`, `/create` or `/edit`.
4. `settings`: a `settings` segment, or a known settings page (`email-theme`, `work-calendar`, `numbering-rules`).
5. `wizard`: `import`, `upload`, `mapping`, `onboard` in the route.
6. `dashboard`: `dashboard`, `overview`, `report`, `analytics`, `usage`, `health`, `stats`, `town`, `pipeline`,
   `planner`, `schedule`, `calendar` in the route.
7. `detail`: the last segment is dynamic (`[id]`); `detail (sub-page)`: a page under a dynamic segment.
8. `list`: everything else.

| Archetype | Pages |
| --- | --- |
| list | 177 |
| detail | 86 |
| detail (sub-page) | 23 |
| form | 55 |
| settings | 17 |
| dashboard | 14 |
| wizard | 9 |
| redirect | 6 |
| demo (retire) | 82 |
| **Total** | **469** |

## By feature area

| Area | Pages | list | detail | form | settings | dashboard | wizard | other |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `(home)` | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| `account` | 34 | 0 | 0 | 0 | 0 | 0 | 0 | 34 |
| `auth` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| `complaint-management` | 8 | 3 | 3 | 2 | 0 | 0 | 0 | 0 |
| `connect` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| `dark-sidebar` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| `dealer-kit` | 20 | 13 | 6 | 1 | 0 | 0 | 0 | 0 |
| `finance` | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| `forms-management` | 5 | 1 | 2 | 2 | 0 | 0 | 0 | 0 |
| `i18n-test` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| `ideas` | 5 | 3 | 2 | 0 | 0 | 0 | 0 | 0 |
| `integration-management` | 5 | 3 | 2 | 0 | 0 | 0 | 0 | 0 |
| `inventory-management` | 13 | 8 | 3 | 2 | 0 | 0 | 0 | 0 |
| `marketing-management` | 10 | 5 | 2 | 3 | 0 | 0 | 0 | 0 |
| `master-data-management` | 36 | 18 | 12 | 6 | 0 | 0 | 0 | 0 |
| `my-requests` | 13 | 3 | 5 | 5 | 0 | 0 | 0 | 0 |
| `network` | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 12 |
| `order-management` | 15 | 5 | 4 | 6 | 0 | 0 | 0 | 0 |
| `procurement-management` | 40 | 10 | 13 | 14 | 0 | 1 | 2 | 0 |
| `project-sales` | 54 | 17 | 24 | 6 | 0 | 3 | 0 | 4 |
| `public-profile` | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 19 |
| `resource-management` | 7 | 6 | 1 | 0 | 0 | 0 | 0 | 0 |
| `sales` | 15 | 11 | 3 | 1 | 0 | 0 | 0 | 0 |
| `scm` | 18 | 8 | 6 | 0 | 0 | 2 | 0 | 2 |
| `sla-management` | 14 | 8 | 3 | 2 | 0 | 1 | 0 | 0 |
| `store-admin` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| `store-client` | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 12 |
| `system-management` | 49 | 32 | 3 | 0 | 3 | 6 | 5 | 0 |
| `ticket-management` | 3 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| `town` | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| `user-management` | 43 | 15 | 10 | 2 | 14 | 0 | 2 | 0 |
| `workflow-forms-management` | 7 | 2 | 3 | 2 | 0 | 0 | 0 | 0 |

## Every page

### `(home)` (1)

| Route | Archetype |
| --- | --- |
| `/` | list |

### `account` (34)

| Route | Archetype |
| --- | --- |
| `/account/activity` | demo (retire) |
| `/account/api-keys` | demo (retire) |
| `/account/appearance` | demo (retire) |
| `/account/billing/basic` | demo (retire) |
| `/account/billing/enterprise` | demo (retire) |
| `/account/billing/history` | demo (retire) |
| `/account/billing/plans` | demo (retire) |
| `/account/home/company-profile` | demo (retire) |
| `/account/home/get-started` | demo (retire) |
| `/account/home/settings-enterprise` | demo (retire) |
| `/account/home/settings-modal` | demo (retire) |
| `/account/home/settings-plain` | demo (retire) |
| `/account/home/settings-sidebar` | demo (retire) |
| `/account/home/user-profile` | demo (retire) |
| `/account/integrations` | demo (retire) |
| `/account/invite-a-friend` | demo (retire) |
| `/account/members/import-members` | demo (retire) |
| `/account/members/members-starter` | demo (retire) |
| `/account/members/permissions-check` | demo (retire) |
| `/account/members/permissions-toggle` | demo (retire) |
| `/account/members/roles` | demo (retire) |
| `/account/members/team-info` | demo (retire) |
| `/account/members/team-members` | demo (retire) |
| `/account/members/team-starter` | demo (retire) |
| `/account/members/teams` | demo (retire) |
| `/account/notifications` | demo (retire) |
| `/account/security/allowed-ip-addresses` | demo (retire) |
| `/account/security/backup-and-recovery` | demo (retire) |
| `/account/security/current-sessions` | demo (retire) |
| `/account/security/device-management` | demo (retire) |
| `/account/security/get-started` | demo (retire) |
| `/account/security/overview` | demo (retire) |
| `/account/security/privacy-settings` | demo (retire) |
| `/account/security/security-log` | demo (retire) |

### `auth` (3)

| Route | Archetype |
| --- | --- |
| `/auth/account-deactivated` | list |
| `/auth/get-started` | list |
| `/auth/welcome-message` | list |

### `complaint-management` (8)

| Route | Archetype |
| --- | --- |
| `/complaint-management/complaint-resolutions` | list |
| `/complaint-management/complaint-resolutions/[id]` | detail |
| `/complaint-management/complaint-root-causes` | list |
| `/complaint-management/complaint-root-causes/[id]` | detail |
| `/complaint-management/complaints` | list |
| `/complaint-management/complaints/[id]` | detail |
| `/complaint-management/complaints/[id]/edit` | form |
| `/complaint-management/complaints/new` | form |

### `connect` (1)

| Route | Archetype |
| --- | --- |
| `/connect/claude` | demo (retire) |

### `dark-sidebar` (1)

| Route | Archetype |
| --- | --- |
| `/dark-sidebar` | demo (retire) |

### `dealer-kit` (20)

| Route | Archetype |
| --- | --- |
| `/dealer-kit` | list |
| `/dealer-kit/accessory-templates` | list |
| `/dealer-kit/brochure-images` | list |
| `/dealer-kit/bundles` | list |
| `/dealer-kit/collections` | list |
| `/dealer-kit/design` | list |
| `/dealer-kit/design/summary` | list |
| `/dealer-kit/editions` | list |
| `/dealer-kit/editions/[editionId]` | detail |
| `/dealer-kit/flyer-readings` | list |
| `/dealer-kit/flyer-readings/[readingId]` | detail |
| `/dealer-kit/pages/[pageId]` | detail |
| `/dealer-kit/price-tag-requests` | list |
| `/dealer-kit/price-tag-requests/[id]` | detail |
| `/dealer-kit/price-tag-requests/[id]/design` | detail (sub-page) |
| `/dealer-kit/price-tag-requests/new` | form |
| `/dealer-kit/tag-sizes` | list |
| `/dealer-kit/tag-templates` | list |
| `/dealer-kit/tag-templates/[id]` | detail |
| `/dealer-kit/tile-designs` | list |

### `finance` (2)

| Route | Archetype |
| --- | --- |
| `/finance/billing-documents` | list |
| `/finance/billing-documents/[id]` | detail |

### `forms-management` (5)

| Route | Archetype |
| --- | --- |
| `/forms-management/forms` | list |
| `/forms-management/forms/[id]` | detail |
| `/forms-management/forms/[id]/builder` | detail (sub-page) |
| `/forms-management/forms/[id]/edit` | form |
| `/forms-management/forms/new` | form |

### `i18n-test` (1)

| Route | Archetype |
| --- | --- |
| `/i18n-test` | demo (retire) |

### `ideas` (5)

| Route | Archetype |
| --- | --- |
| `/ideas` | list |
| `/ideas/[id]` | detail |
| `/ideas/board` | list |
| `/ideas/portal` | list |
| `/ideas/portal/[id]` | detail |

### `integration-management` (5)

| Route | Archetype |
| --- | --- |
| `/integration-management/integration-logs` | list |
| `/integration-management/integration-logs/[id]` | detail |
| `/integration-management/integrations` | list |
| `/integration-management/integrations/[id]` | detail |
| `/integration-management/whatsapp-templates` | list |

### `inventory-management` (13)

| Route | Archetype |
| --- | --- |
| `/inventory-management/stock` | list |
| `/inventory-management/stock-batches` | list |
| `/inventory-management/stock-ledger` | list |
| `/inventory-management/stock-position` | list |
| `/inventory-management/stock-status` | list |
| `/inventory-management/stock-transfers` | list |
| `/inventory-management/stock-transfers/[id]` | detail |
| `/inventory-management/stock/[productId]/[warehouseId]` | detail |
| `/inventory-management/storage-zones` | list |
| `/inventory-management/warehouses` | list |
| `/inventory-management/warehouses/[id]` | detail |
| `/inventory-management/warehouses/[id]/edit` | form |
| `/inventory-management/warehouses/new` | form |

### `marketing-management` (10)

| Route | Archetype |
| --- | --- |
| `/marketing-management/campaigns` | list |
| `/marketing-management/campaigns/[id]` | detail |
| `/marketing-management/campaigns/new` | form |
| `/marketing-management/promotion-attachments` | list |
| `/marketing-management/promotion-products` | list |
| `/marketing-management/promotion-types` | list |
| `/marketing-management/promotions` | list |
| `/marketing-management/promotions/[id]` | detail |
| `/marketing-management/promotions/[id]/edit` | form |
| `/marketing-management/promotions/new` | form |

### `master-data-management` (36)

| Route | Archetype |
| --- | --- |
| `/master-data-management/accessories` | list |
| `/master-data-management/brands` | list |
| `/master-data-management/brands/[id]` | detail |
| `/master-data-management/brands/[id]/edit` | form |
| `/master-data-management/brands/new` | form |
| `/master-data-management/certificates` | list |
| `/master-data-management/certificates/[id]` | detail |
| `/master-data-management/certificates/links` | list |
| `/master-data-management/countries` | list |
| `/master-data-management/flyer-spec-proposals` | list |
| `/master-data-management/flyer-spec-proposals/[readingId]` | detail |
| `/master-data-management/item-classes` | list |
| `/master-data-management/item-classes/[id]` | detail |
| `/master-data-management/lookup-sets` | list |
| `/master-data-management/lookup-sets/[id]` | detail |
| `/master-data-management/payment-terms` | list |
| `/master-data-management/product-attachments` | list |
| `/master-data-management/product-categories` | list |
| `/master-data-management/product-categories/[id]` | detail |
| `/master-data-management/product-sets` | list |
| `/master-data-management/product-sets/[id]` | detail |
| `/master-data-management/product-sets/proposals` | list |
| `/master-data-management/product-specifications` | list |
| `/master-data-management/product-specifications/[specKey]` | detail |
| `/master-data-management/products` | list |
| `/master-data-management/products/[id]` | detail |
| `/master-data-management/products/[id]/edit` | form |
| `/master-data-management/products/catalogue-photos/[id]` | detail |
| `/master-data-management/products/new` | form |
| `/master-data-management/sales-agents` | list |
| `/master-data-management/sales-agents/[id]` | detail |
| `/master-data-management/spec-verification` | list |
| `/master-data-management/units-of-measure` | list |
| `/master-data-management/units-of-measure/[id]` | detail |
| `/master-data-management/units-of-measure/[id]/edit` | form |
| `/master-data-management/units-of-measure/new` | form |

### `my-requests` (13)

| Route | Archetype |
| --- | --- |
| `/my-requests` | list |
| `/my-requests/[type]/[id]` | detail |
| `/my-requests/[type]/new` | form |
| `/my-requests/new_product_application/[id]` | detail |
| `/my-requests/new_product_application/new` | form |
| `/my-requests/price_tag_request` | list |
| `/my-requests/price_tag_request/[id]` | detail |
| `/my-requests/price_tag_request/new` | form |
| `/my-requests/sales_opportunity/[id]` | detail |
| `/my-requests/sales_opportunity/new` | form |
| `/my-requests/sample_request/[id]` | detail |
| `/my-requests/sample_request/new` | form |
| `/my-requests/verify` | list |

### `network` (12)

| Route | Archetype |
| --- | --- |
| `/network/get-started` | demo (retire) |
| `/network/user-cards/author` | demo (retire) |
| `/network/user-cards/mini-cards` | demo (retire) |
| `/network/user-cards/nft` | demo (retire) |
| `/network/user-cards/social` | demo (retire) |
| `/network/user-cards/team-crew` | demo (retire) |
| `/network/user-table/app-roster` | demo (retire) |
| `/network/user-table/market-authors` | demo (retire) |
| `/network/user-table/saas-users` | demo (retire) |
| `/network/user-table/store-clients` | demo (retire) |
| `/network/user-table/team-crew` | demo (retire) |
| `/network/user-table/visitors` | demo (retire) |

### `order-management` (15)

| Route | Archetype |
| --- | --- |
| `/order-management/branches` | list |
| `/order-management/customer-groups` | list |
| `/order-management/customer-groups/[id]` | detail |
| `/order-management/customers` | list |
| `/order-management/customers/[id]` | detail |
| `/order-management/customers/[id]/edit` | form |
| `/order-management/customers/new` | form |
| `/order-management/order-statuses` | list |
| `/order-management/order-statuses/[id]` | detail |
| `/order-management/order-statuses/[id]/edit` | form |
| `/order-management/order-statuses/new` | form |
| `/order-management/orders` | list |
| `/order-management/orders/[id]` | detail |
| `/order-management/orders/[id]/edit` | form |
| `/order-management/orders/new` | form |

### `procurement-management` (40)

| Route | Archetype |
| --- | --- |
| `/procurement-management/cost-price-uploads` | wizard |
| `/procurement-management/cost-price-uploads/[id]` | wizard |
| `/procurement-management/grn` | list |
| `/procurement-management/grn/[id]` | detail |
| `/procurement-management/grn/[id]/edit` | form |
| `/procurement-management/grn/new` | form |
| `/procurement-management/new-product-applications` | list |
| `/procurement-management/new-product-applications/[id]` | detail |
| `/procurement-management/new-product-applications/[id]/edit` | form |
| `/procurement-management/new-product-applications/new` | form |
| `/procurement-management/packing-lists` | list |
| `/procurement-management/packing-lists/[id]` | detail |
| `/procurement-management/packing-lists/[id]/documents` | detail (sub-page) |
| `/procurement-management/packing-lists/[id]/lines` | detail (sub-page) |
| `/procurement-management/packing-lists/[id]/proforma-invoices` | detail (sub-page) |
| `/procurement-management/packing-lists/[id]/spo` | detail (sub-page) |
| `/procurement-management/packing-lists/[id]/timeline` | detail (sub-page) |
| `/procurement-management/packing-lists/new` | form |
| `/procurement-management/picking-lines` | list |
| `/procurement-management/product-suppliers` | list |
| `/procurement-management/purchase-requests` | list |
| `/procurement-management/purchase-requests/[id]` | detail |
| `/procurement-management/purchase-requests/[id]/edit` | form |
| `/procurement-management/purchase-requests/new` | form |
| `/procurement-management/spo-allocations` | list |
| `/procurement-management/spo-allocations/[spoNumber]` | detail |
| `/procurement-management/spo-allocations/new` | form |
| `/procurement-management/sponsorship-forms` | list |
| `/procurement-management/sponsorship-forms/[id]` | detail |
| `/procurement-management/sponsorship-forms/[id]/edit` | form |
| `/procurement-management/sponsorship-forms/new` | form |
| `/procurement-management/sponsorship-forms/report` | dashboard |
| `/procurement-management/stock-inquiries` | list |
| `/procurement-management/stock-inquiries/[id]` | detail |
| `/procurement-management/stock-inquiries/[id]/edit` | form |
| `/procurement-management/stock-inquiries/new` | form |
| `/procurement-management/suppliers` | list |
| `/procurement-management/suppliers/[id]` | detail |
| `/procurement-management/suppliers/[id]/edit` | form |
| `/procurement-management/suppliers/new` | form |

### `project-sales` (54)

| Route | Archetype |
| --- | --- |
| `/project-sales/[projectId]` | detail |
| `/project-sales/[projectId]/delivery-schedules/[versionId]` | dashboard |
| `/project-sales/[projectId]/edit` | form |
| `/project-sales/[projectId]/order-inquiries` | detail (sub-page) |
| `/project-sales/[projectId]/pos/[poId]` | detail |
| `/project-sales/[projectId]/purchase-orders/[versionId]` | detail |
| `/project-sales/[projectId]/quotation-documents/[documentId]` | detail |
| `/project-sales/[projectId]/quotation-documents/[documentId]/certification` | detail (sub-page) |
| `/project-sales/[projectId]/quotation-documents/[documentId]/certification/[certificateId]` | detail |
| `/project-sales/[projectId]/quotation-documents/[documentId]/cover-letter` | detail (sub-page) |
| `/project-sales/[projectId]/quotation-documents/[documentId]/edit` | form |
| `/project-sales/[projectId]/quotation-documents/[documentId]/feedback` | detail (sub-page) |
| `/project-sales/[projectId]/quotation-documents/[documentId]/lines` | redirect |
| `/project-sales/[projectId]/quotation-documents/[documentId]/signatures` | detail (sub-page) |
| `/project-sales/[projectId]/quotation-documents/[documentId]/spec-sheet` | detail (sub-page) |
| `/project-sales/[projectId]/quotation-documents/[documentId]/spec-sheet/[sheetId]` | detail |
| `/project-sales/[projectId]/quotation-documents/[documentId]/spec-sheet/[sheetId]/pages/[key]/edit` | redirect |
| `/project-sales/[projectId]/quotation-documents/[documentId]/terms` | detail (sub-page) |
| `/project-sales/[projectId]/quotation-documents/new` | form |
| `/project-sales/[projectId]/sales-orders/[psoId]` | detail |
| `/project-sales/[projectId]/sales-orders/[psoId]/divergence` | detail (sub-page) |
| `/project-sales/[projectId]/sales-orders/[psoId]/revisions` | detail (sub-page) |
| `/project-sales/[projectId]/sales-orders/[psoId]/worksheet` | detail (sub-page) |
| `/project-sales/divergences` | list |
| `/project-sales/fulfilment-planning` | list |
| `/project-sales/lead-acceptance` | list |
| `/project-sales/leads` | list |
| `/project-sales/leads/[leadId]` | detail |
| `/project-sales/my-tasks` | list |
| `/project-sales/new` | form |
| `/project-sales/order-inquiries` | list |
| `/project-sales/order-inquiries/[id]` | detail |
| `/project-sales/parties` | list |
| `/project-sales/parties/[partyId]` | detail |
| `/project-sales/pipeline` | dashboard |
| `/project-sales/planning-changes` | list |
| `/project-sales/plans` | list |
| `/project-sales/price-floors` | list |
| `/project-sales/price-floors/[ruleId]` | detail |
| `/project-sales/pricing` | redirect |
| `/project-sales/projects` | redirect |
| `/project-sales/quotation-templates` | list |
| `/project-sales/reports` | dashboard |
| `/project-sales/sample-requests` | list |
| `/project-sales/sample-requests/[id]` | detail |
| `/project-sales/sample-requests/[id]/edit` | form |
| `/project-sales/sample-requests/new` | form |
| `/project-sales/series` | list |
| `/project-sales/series/[seriesId]` | detail |
| `/project-sales/setup` | list |
| `/project-sales/stock-claims` | list |
| `/project-sales/stock-debt` | list |
| `/project-sales/stock-debt/snapshots` | list |
| `/project-sales/stock-debt/snapshots/[id]` | detail |

### `public-profile` (19)

| Route | Archetype |
| --- | --- |
| `/public-profile/activity` | demo (retire) |
| `/public-profile/campaigns/card` | demo (retire) |
| `/public-profile/campaigns/list` | demo (retire) |
| `/public-profile/empty` | demo (retire) |
| `/public-profile/network` | demo (retire) |
| `/public-profile/profiles/blogger` | demo (retire) |
| `/public-profile/profiles/company` | demo (retire) |
| `/public-profile/profiles/creator` | demo (retire) |
| `/public-profile/profiles/crm` | demo (retire) |
| `/public-profile/profiles/default` | demo (retire) |
| `/public-profile/profiles/feeds` | demo (retire) |
| `/public-profile/profiles/gamer` | demo (retire) |
| `/public-profile/profiles/modal` | demo (retire) |
| `/public-profile/profiles/nft` | demo (retire) |
| `/public-profile/profiles/plain` | demo (retire) |
| `/public-profile/projects/2-columns` | demo (retire) |
| `/public-profile/projects/3-columns` | demo (retire) |
| `/public-profile/teams` | demo (retire) |
| `/public-profile/works` | demo (retire) |

### `resource-management` (7)

| Route | Archetype |
| --- | --- |
| `/resource-management/attachment-directories` | list |
| `/resource-management/attachment-types` | list |
| `/resource-management/attachments` | list |
| `/resource-management/attachments/[id]` | detail |
| `/resource-management/document-access` | list |
| `/resource-management/smart-linkage` | list |
| `/resource-management/trash` | list |

### `sales` (15)

| Route | Archetype |
| --- | --- |
| `/sales/customer-asks` | list |
| `/sales/dealer-access` | list |
| `/sales/leaderboard` | list |
| `/sales/opportunities` | list |
| `/sales/opportunities/[id]` | detail |
| `/sales/sales-and-outstanding` | list |
| `/sales/sales-by-debtor-type` | list |
| `/sales/set-apart-customers` | list |
| `/sales/targets` | list |
| `/sales/targets/[id]` | detail |
| `/sales/targets/new` | form |
| `/sales/teams` | list |
| `/sales/teams/[id]` | detail |
| `/sales/top-selling-items` | list |
| `/sales/yearly-comparison` | list |

### `scm` (18)

| Route | Archetype |
| --- | --- |
| `/scm` | list |
| `/scm/consignments` | list |
| `/scm/consignments/[id]` | detail |
| `/scm/loading-plan` | dashboard |
| `/scm/loading-plan/[id]` | detail |
| `/scm/low-stock-report` | redirect |
| `/scm/low-stock-report/[runId]` | dashboard |
| `/scm/market-signals` | list |
| `/scm/policies` | list |
| `/scm/proforma-invoices` | list |
| `/scm/proforma-invoices/[id]` | detail |
| `/scm/purchase-orders` | list |
| `/scm/purchase-orders/[id]` | detail |
| `/scm/reorder` | redirect |
| `/scm/reorder/[id]` | detail |
| `/scm/sales-orders` | list |
| `/scm/sales-orders/[id]` | detail |
| `/scm/simulation` | list |

### `sla-management` (14)

| Route | Archetype |
| --- | --- |
| `/sla-management/conversation-sla-tracking` | list |
| `/sla-management/conversation-sla-tracking/[id]` | detail |
| `/sla-management/conversations` | list |
| `/sla-management/escalation-logs` | list |
| `/sla-management/form-sla-config` | list |
| `/sla-management/form-sla-tracking` | list |
| `/sla-management/form-sla-tracking/[id]` | detail |
| `/sla-management/kpi-dashboard` | dashboard |
| `/sla-management/message-snippets` | list |
| `/sla-management/sla-policies` | list |
| `/sla-management/sla-policies/[id]` | detail |
| `/sla-management/sla-policies/[id]/edit` | form |
| `/sla-management/sla-policies/new` | form |
| `/sla-management/team-pending` | list |

### `store-admin` (2)

| Route | Archetype |
| --- | --- |
| `/store-admin/dashboard` | demo (retire) |
| `/store-admin/inventory/all-products` | demo (retire) |

### `store-client` (12)

| Route | Archetype |
| --- | --- |
| `/store-client/cart` | demo (retire) |
| `/store-client/checkout/order-placed` | demo (retire) |
| `/store-client/checkout/order-summary` | demo (retire) |
| `/store-client/checkout/payment-method` | demo (retire) |
| `/store-client/checkout/shipping-info` | demo (retire) |
| `/store-client/home` | demo (retire) |
| `/store-client/my-orders` | demo (retire) |
| `/store-client/order-receipt` | demo (retire) |
| `/store-client/product-details` | demo (retire) |
| `/store-client/search-results-grid` | demo (retire) |
| `/store-client/search-results-list` | demo (retire) |
| `/store-client/wishlist` | demo (retire) |

### `system-management` (49)

| Route | Archetype |
| --- | --- |
| `/system-management/activity` | list |
| `/system-management/ai-assistant` | list |
| `/system-management/ai-assistant/model-prices` | list |
| `/system-management/ai-assistant/prompts` | list |
| `/system-management/ai-assistant/prompts/[name]` | detail |
| `/system-management/ai-assistant/usage` | dashboard |
| `/system-management/ai-assistant/usage/trace/[messageId]` | dashboard |
| `/system-management/ai-assistant/wishlist` | list |
| `/system-management/api-call-logs` | list |
| `/system-management/app-store` | list |
| `/system-management/app-store/bundles` | list |
| `/system-management/audit-logs` | list |
| `/system-management/automation` | list |
| `/system-management/automation/[id]` | detail |
| `/system-management/bot-failures` | list |
| `/system-management/chat-history` | list |
| `/system-management/chat-overview` | dashboard |
| `/system-management/chatbot-console` | list |
| `/system-management/chatbot-domains` | list |
| `/system-management/chatbot-entity-kinds` | list |
| `/system-management/chatbot-status-words` | list |
| `/system-management/client-errors` | list |
| `/system-management/companies` | list |
| `/system-management/email-event-configs` | list |
| `/system-management/email-outbox` | list |
| `/system-management/email-templates` | list |
| `/system-management/email-templates/[id]` | detail |
| `/system-management/email-theme` | settings |
| `/system-management/embeddings` | list |
| `/system-management/health` | dashboard |
| `/system-management/import-field-aliases` | wizard |
| `/system-management/import-jobs` | wizard |
| `/system-management/import-jobs/[id]` | wizard |
| `/system-management/import-logs` | wizard |
| `/system-management/import-logs/[id]` | wizard |
| `/system-management/mcp-tools` | list |
| `/system-management/numbering-rules` | settings |
| `/system-management/outgoing-mails` | list |
| `/system-management/respond-contacts` | list |
| `/system-management/respond-outbox` | list |
| `/system-management/respond-workspaces` | list |
| `/system-management/scheduled-tasks` | dashboard |
| `/system-management/scheduled-tasks/[id]` | dashboard |
| `/system-management/status-graphs` | list |
| `/system-management/top-asks` | list |
| `/system-management/topic-audit` | list |
| `/system-management/tracking-validation` | list |
| `/system-management/translations` | list |
| `/system-management/work-calendar` | settings |

### `ticket-management` (3)

| Route | Archetype |
| --- | --- |
| `/ticket-management/tickets` | list |
| `/ticket-management/tickets/[id]` | detail |
| `/ticket-management/tickets/new` | form |

### `town` (1)

| Route | Archetype |
| --- | --- |
| `/town` | dashboard |

### `user-management` (43)

| Route | Archetype |
| --- | --- |
| `/user-management/access-agents` | list |
| `/user-management/access-agents/[id]` | detail |
| `/user-management/access-agents/[id]/edit` | form |
| `/user-management/access-agents/new` | form |
| `/user-management/account` | list |
| `/user-management/account/logs` | list |
| `/user-management/account/security` | list |
| `/user-management/contact-access-agents` | list |
| `/user-management/contact-access-types` | list |
| `/user-management/contact-tags` | list |
| `/user-management/contact-tags/[id]` | detail |
| `/user-management/contacts` | list |
| `/user-management/contacts/[id]` | detail |
| `/user-management/contacts/[id]/access` | detail (sub-page) |
| `/user-management/contacts/[id]/chat` | detail (sub-page) |
| `/user-management/contacts/[id]/chatbot` | detail (sub-page) |
| `/user-management/contacts/[id]/routing` | detail (sub-page) |
| `/user-management/contacts/access-sheet` | list |
| `/user-management/logs` | list |
| `/user-management/market-segments` | list |
| `/user-management/onboarding-requests` | wizard |
| `/user-management/onboarding-requests/[id]` | wizard |
| `/user-management/permissions` | list |
| `/user-management/roles` | list |
| `/user-management/settings` | settings |
| `/user-management/settings/chatbot` | settings |
| `/user-management/settings/chatbot-media` | settings |
| `/user-management/settings/complaints` | settings |
| `/user-management/settings/embeddings` | settings |
| `/user-management/settings/integrations` | settings |
| `/user-management/settings/notifications` | settings |
| `/user-management/settings/portal-revisions` | settings |
| `/user-management/settings/search-ranking` | settings |
| `/user-management/settings/smtp` | settings |
| `/user-management/settings/social` | settings |
| `/user-management/settings/spec-visibility` | settings |
| `/user-management/settings/stock-visibility` | settings |
| `/user-management/settings/system-health` | settings |
| `/user-management/teams` | list |
| `/user-management/teams/[id]` | detail |
| `/user-management/users` | list |
| `/user-management/users/[id]` | detail |
| `/user-management/users/[id]/logs` | detail (sub-page) |

### `workflow-forms-management` (7)

| Route | Archetype |
| --- | --- |
| `/workflow-forms-management/definitions` | list |
| `/workflow-forms-management/definitions/[id]` | detail |
| `/workflow-forms-management/forms/[definitionId]/new` | form |
| `/workflow-forms-management/forms/[definitionId]/submissions` | detail (sub-page) |
| `/workflow-forms-management/submissions` | list |
| `/workflow-forms-management/submissions/[id]` | detail |
| `/workflow-forms-management/submissions/new` | form |
