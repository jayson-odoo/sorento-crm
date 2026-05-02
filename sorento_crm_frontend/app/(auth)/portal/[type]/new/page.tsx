'use client';

import { use } from 'react';
import { notFound } from 'next/navigation';
import { SubmissionForm } from '../../components/SubmissionForm';
import { PortalSubmissionKind } from '../../lib/portal-client';

const VALID: PortalSubmissionKind[] = [
  'complaint',
  'stock_inquiry',
  'purchase_request',
  'sponsorship_form',
];

export default function PortalNewSubmissionPage({
  params,
}: {
  params: Promise<{ type: string }>;
}) {
  const { type } = use(params);
  if (!VALID.includes(type as PortalSubmissionKind)) {
    notFound();
  }
  return <SubmissionForm kind={type as PortalSubmissionKind} />;
}
