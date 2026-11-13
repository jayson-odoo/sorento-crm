import { redirect } from 'next/navigation';

/** Moved (hand-test round G3): the request's pages live under Procurement. */
export default function OldNewSparePartRequestPage() {
  redirect('/procurement-management/spare-part-requests/new');
}
