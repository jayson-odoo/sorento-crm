'use client';

import { use } from 'react';
import { notFound } from 'next/navigation';
import { SubmissionForm } from '../../../../components/SubmissionForm';
import { PortalSubmissionKind, isSubmissionKind } from '../../../../lib/portal-client';

// UUIDs are hex + dashes. Status-message links occasionally arrive with trailing
// sentence punctuation absorbed by WhatsApp's link detection (e.g. `…/{uuid}:`),
// which would reach the backend as `%3A` and 500 on the UUID parse. Trim anything
// past the valid id characters defensively.
function sanitizeId(raw: string): string {
  return (raw || '').replace(/[^0-9a-fA-F-].*$/, '');
}

export default function PortalSlugEditSubmissionPage({
  params,
}: {
  params: Promise<{ slug: string; type: string; id: string }>;
}) {
  const { slug, type, id } = use(params);
  if (!isSubmissionKind(type)) {
    notFound();
  }
  return (
    <SubmissionForm
      kind={type as PortalSubmissionKind}
      submissionId={sanitizeId(id)}
      slug={slug}
    />
  );
}
