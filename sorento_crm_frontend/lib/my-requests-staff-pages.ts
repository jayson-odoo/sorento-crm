/**
 * PORTAL-P4-REQUESTS: the four request forms a salesperson opens from MY REQUESTS on the STAFF pages,
 * which the server narrows to their own rows (`<form>.view_own`). The other portal kinds still render
 * the portal form inside /my-requests until their own slices. Read by the menu and by the
 * /my-requests deep-link redirects.
 */
export const MY_REQUEST_STAFF_PAGES: Readonly<Record<string, { path: string; permission: string }>> = {
  stock_inquiry: {
    path: '/procurement-management/stock-inquiries',
    permission: 'procurement.stock_inquiries.view_own',
  },
  complaint: {
    path: '/complaint-management/complaints',
    permission: 'complaint_management.complaints.view_own',
  },
  purchase_request: {
    path: '/procurement-management/purchase-requests',
    permission: 'procurement.purchase_requests.view_own',
  },
  sponsorship_form: {
    path: '/procurement-management/sponsorship-forms',
    permission: 'procurement.sponsorship_forms.view_own',
  },
};

/** The staff list path for a kind that moved, or null for a kind still served under /my-requests. */
export function myRequestStaffPath(kind: string | null | undefined): string | null {
  return (kind && MY_REQUEST_STAFF_PAGES[kind]?.path) || null;
}
