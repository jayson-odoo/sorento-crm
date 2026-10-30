/**
 * PORTAL-P4-REQUESTS: the request forms a salesperson opens from MY REQUESTS on the STAFF pages,
 * which the server narrows to their own rows (`<form>.view_own`). Read by the menu, by the
 * /my-requests redirects and by the portal-to-CRM twin paths. `create`: the grant their list's
 * Create needs (`MyRequestPortalList`), the server's write slug for the form.
 */
export const MY_REQUEST_STAFF_PAGES: Readonly<
  Record<string, { path: string; permission: string; create: string }>
> = {
  stock_inquiry: {
    path: '/procurement-management/stock-inquiries',
    permission: 'procurement.stock_inquiries.view_own',
    create: 'procurement.stock_inquiries.add',
  },
  complaint: {
    path: '/complaint-management/complaints',
    permission: 'complaint_management.complaints.view_own',
    create: 'complaint_management.complaints.add',
  },
  purchase_request: {
    path: '/procurement-management/purchase-requests',
    permission: 'procurement.purchase_requests.view_own',
    create: 'procurement.purchase_requests.add',
  },
  sponsorship_form: {
    path: '/procurement-management/sponsorship-forms',
    permission: 'procurement.sponsorship_forms.view_own',
    create: 'procurement.sponsorship_forms.add',
  },
  sample_request: {
    path: '/project-sales/sample-requests',
    permission: 'projects.sample_requests.view_own',
    create: 'projects.sample_requests.create',
  },
  new_product_application: {
    path: '/procurement-management/new-product-applications',
    permission: 'procurement.new_product_applications.view_own',
    create: 'procurement.new_product_applications.create',
  },
  // No staff /new page: the Log opportunity modal opens on the list.
  sales_opportunity: {
    path: '/sales/opportunities',
    permission: 'sales.opportunities.view_own',
    create: 'sales.opportunities.add',
  },
  // Dealer Kit > Room Designer > Price Tag Requests: New / Edit are the request page in edit mode.
  price_tag_request: {
    path: '/dealer-kit/price-tag-requests',
    permission: 'dealer_kit.price_tag_requests.view_own',
    create: 'dealer_kit.price_tag_requests.create',
  },
};

/** The staff list path for a kind that moved, or null for a kind still served under /my-requests. */
export function myRequestStaffPath(kind: string | null | undefined): string | null {
  return (kind && MY_REQUEST_STAFF_PAGES[kind]?.path) || null;
}

/** Trim trailing punctuation a pasted link can absorb off a record id. */
export function sanitizeId(raw: string): string {
  return (raw || '').replace(/[^0-9a-fA-F-].*$/, '');
}
