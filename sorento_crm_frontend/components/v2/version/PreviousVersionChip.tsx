'use client';

import { Badge } from '@/components/ui/badge';
import { useUiVersion } from './useUiVersion';

/** Marks a screen with no v2 client yet, inside the v2 shell; only the v2 cohort sees it (B-10). */
export function PreviousVersionChip() {
  const { uiV2Available } = useUiVersion();
  if (!uiV2Available) return null;
  return (
    <Badge variant="secondary" appearance="light" size="sm">
      Previous-version screen
    </Badge>
  );
}
