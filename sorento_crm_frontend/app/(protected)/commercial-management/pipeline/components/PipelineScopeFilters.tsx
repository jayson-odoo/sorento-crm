'use client';

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import type { ScopeParam } from '../services/commercialPipelineApi';

export function PipelineScopeFilters({
  scope,
  onScopeChange,
}: {
  scope: ScopeParam;
  onScopeChange: (v: ScopeParam) => void;
}) {
  return (
    <ToggleGroup
      type="single"
      value={scope}
      onValueChange={(v) => {
        if (v === 'mine' || v === 'all') onScopeChange(v);
      }}
      className="justify-start"
    >
      <ToggleGroupItem value="all" aria-label="All records">
        All
      </ToggleGroupItem>
      <ToggleGroupItem value="mine" aria-label="Assigned to me">
        Assigned to me
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
