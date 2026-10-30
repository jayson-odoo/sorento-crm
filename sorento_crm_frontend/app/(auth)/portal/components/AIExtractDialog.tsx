'use client';

/**
 * The portal's AI extract popup: the shared dialog (`components/common/ai-extract`) with the
 * portal's extract call and token-authenticated preview reader wired in. Behaviour is the
 * shared dialog's, unchanged.
 */
import { useCallback, type ComponentProps } from 'react';

import { AIExtractDialog as SharedAIExtractDialog } from '@/components/common/ai-extract/AIExtractDialog';

import { AI_EXTRACT_FORM_KEYS, PortalLandingKind } from '../lib/portal-client';
import { useSubmissionClient, useSubmissionFetchBytes } from '../lib/submission-client';

export type { AIExtractApplyPayload } from '@/components/common/ai-extract/AIExtractDialog';

type SharedProps = ComponentProps<typeof SharedAIExtractDialog>;

type Props = Omit<SharedProps, 'kind' | 'extract' | 'fetchBytes'> & {
  kind: PortalLandingKind;
};

export function AIExtractDialog({ kind, ...rest }: Props) {
  // The API this dialog talks to (R1): portal-client, or the CRM's My Requests client.
  const client = useSubmissionClient();
  const fetchBytes = useSubmissionFetchBytes();
  const extract = useCallback(
    (files: File[]) => client.aiExtractFromFiles(AI_EXTRACT_FORM_KEYS[kind], files),
    [kind, client],
  );
  return (
    <SharedAIExtractDialog {...rest} kind={kind} extract={extract} fetchBytes={fetchBytes} />
  );
}
