'use client';

import { useMemo } from 'react';
import type { SubmissionExtraTab } from '@/app/(auth)/portal/lib/submission-client';
import ComplaintFulfilmentOrdersSection from './ComplaintFulfilmentOrdersSection';

/** The one tab a salesperson's saved complaint has beyond the portal's form: its fulfilment DOs, read-only (L3). */
export function useComplaintFulfilmentTabs(complaintId?: string): SubmissionExtraTab[] | undefined {
  return useMemo(
    () =>
      complaintId
        ? [
            {
              value: 'fulfilment-dos',
              label: 'Fulfilment DOs',
              content: <ComplaintFulfilmentOrdersSection complaintId={complaintId} readOnly />,
            },
          ]
        : undefined,
    [complaintId],
  );
}
