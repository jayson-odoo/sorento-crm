'use client';

/**
 * The portal's AI extract popup: the shared dialog (`components/common/ai-extract`) with the
 * portal's extract call and token-authenticated preview reader wired in. Behaviour is the
 * shared dialog's, unchanged.
 */
import { useCallback, type ComponentProps } from 'react';

import { AIExtractDialog as SharedAIExtractDialog } from '@/components/common/ai-extract/AIExtractDialog';

import {
  AI_EXTRACT_FORM_KEYS,
  PortalLandingKind,
  aiExtractFromFiles,
} from '../lib/portal-client';
import { portalFetchBytes } from '../lib/portal-preview';

export type { AIExtractApplyPayload } from '@/components/common/ai-extract/AIExtractDialog';

type SharedProps = ComponentProps<typeof SharedAIExtractDialog>;

type Props = Omit<SharedProps, 'kind' | 'extract' | 'fetchBytes'> & {
  kind: PortalLandingKind;
};

export function AIExtractDialog({ kind, ...rest }: Props) {
  const extract = useCallback(
    (files: File[]) => aiExtractFromFiles(AI_EXTRACT_FORM_KEYS[kind], files),
    [kind],
  );
  return (
    <SharedAIExtractDialog {...rest} kind={kind} extract={extract} fetchBytes={portalFetchBytes} />
  );
}
