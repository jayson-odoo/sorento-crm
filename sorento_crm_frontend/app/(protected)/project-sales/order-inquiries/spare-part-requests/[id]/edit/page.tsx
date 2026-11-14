import { redirect } from 'next/navigation';

/** Moved (hand-test round G3): the request's pages live under Procurement. */
export default async function OldEditSparePartRequestPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/procurement-management/spare-part-requests/${encodeURIComponent(id)}/edit`);
}
