/**
 * The demand drill's click-through to the project-sales Order Inquiry worklist
 * (captain, 20 Aug: "each SO line ... should navigate to the Order Inquiry worklist
 * scoped to that SO").
 *
 * `query` is the SAME free-text filter key `OrderInquiryWorklistService._base` already
 * accepts server-side (`app/services/order_inquiry_worklist_service.py`) - it matches the
 * SO number, item code, product code/name, customer and project in one `ILIKE`, so an SO
 * number scopes the worklist to exactly that line's inquiry the moment the param is read.
 *
 * HALF-WIRED ON PURPOSE: `OrderInquiriesClient.tsx` (owned by another lane; out of scope
 * here) currently URL-syncs only `view` / `rows` / `granularity` - its `query` search box
 * is local `useState('')`, not sourced from `useSearchParams()`. So this link is correct
 * and ready today but lands on an UNFILTERED worklist until that page reads `?query=`
 * on mount. Do not rename this param without updating the backend filter it mirrors.
 */
export function orderInquiryWorklistHref(soNumber: string): string {
  return `/project-sales/order-inquiries?query=${encodeURIComponent(soNumber)}`;
}
