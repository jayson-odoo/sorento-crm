'use client';

import { Building2, Globe2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

/**
 * AC-P10 scope indicator. Deliberately exempt from AC-X1 (no explanatory prose
 * on screens): it is not describing the feature, it is naming which set of rows
 * the tab is editing. Policies are company-scoped; Kinds and Rules are one
 * vocabulary shared by every company, and an admin who assumes otherwise will
 * edit Mocha's mapping from inside Sorento without noticing.
 */
export function ScopeBadge({ scope }: { scope: { kind: 'company'; name: string } | { kind: 'shared' } }) {
  if (scope.kind === 'company') {
    return (
      <Badge variant="secondary" appearance="light" size="md" className="shrink-0">
        <Building2 className="size-3.5" />
        {scope.name}
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" appearance="light" size="md" className="shrink-0">
      <Globe2 className="size-3.5" />
      Shared across companies
    </Badge>
  );
}
