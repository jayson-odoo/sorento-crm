'use client';

import { Filter } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { ScmFilters } from '../services/scmDashboardService';
import { isAllScope, isFocusedScope, scopeSummary } from '../lib/scope';

/**
 * Transparency indicator for the lifecycle scope.
 *
 * The dashboard defaults to the FOCUSED view (active + ongoing), which silently
 * shrinks the headline counts (e.g. Stockouts 2,688 → 2,454). This chip makes
 * that active narrowing visible right next to the tiles and offers a one-click
 * "Show all" to widen both filters - so the user never wonders where SKUs went.
 * When already showing everything it flips to a "Back to focused" reset.
 */
export function ScmScopeChip({
  filters,
  onChange,
}: {
  filters: ScmFilters;
  onChange: (next: ScmFilters) => void;
}) {
  const focused = isFocusedScope(filters);
  const all = isAllScope(filters);

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant="secondary" appearance="light" size="md">
        <Filter className="size-3.5" />
        {scopeSummary(filters)}
      </Badge>
      {focused ? (
        <Button
          variant="outline"
          size="sm"
          onClick={() => onChange({ ...filters, activeStatus: 'all', lifecycle: 'all' })}
        >
          Show all
        </Button>
      ) : (
        <Button
          variant="outline"
          size="sm"
          onClick={() => onChange({ ...filters, activeStatus: 'active', lifecycle: 'ongoing' })}
        >
          {all ? 'Back to focused' : 'Reset to focused'}
        </Button>
      )}
    </div>
  );
}
