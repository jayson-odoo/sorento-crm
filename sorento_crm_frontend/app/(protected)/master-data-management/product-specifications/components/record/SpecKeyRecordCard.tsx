'use client';

import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import DetailActions from '@/components/common/DetailActions';
import type { RecordAction } from '@/components/common/recordActions';
import { specTypeLabel } from '../../lib/specTypeLabel';
import type { SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

/**
 * The record card (B.1): label as title, the slug as secondary text, type and
 * source pills, unit as a field. Label and unit swap for inputs in edit mode - the
 * only two identity fields B.2's PATCH carries, so they are the only two that move.
 * `DetailActions` in the design-language order: pager, gear, primary.
 */
export function SpecKeyRecordCard({
  row,
  mode,
  draft,
  setDraft,
  pagerNode,
  actions,
  pending,
  primary,
}: {
  row: SpecRegistryKey;
  mode: 'view' | 'edit';
  draft: SpecKeyDraft | null;
  setDraft: (updater: (draft: SpecKeyDraft) => SpecKeyDraft) => void;
  pagerNode: ReactNode;
  actions: RecordAction[];
  pending: ReactNode;
  primary: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="block py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {mode === 'edit' && draft ? (
                <Input
                  value={draft.label}
                  onChange={(event) =>
                    setDraft((d) => ({ ...d, label: event.target.value }))
                  }
                  className="h-8 max-w-xs text-base font-semibold"
                  aria-label="Label"
                  maxLength={100}
                />
              ) : (
                <CardTitle className="text-lg">{row.label}</CardTitle>
              )}
              <Badge variant="secondary" appearance="light" size="sm" shape="circle">
                {specTypeLabel(row.data_type)}
              </Badge>
              <Badge
                variant={row.source === 'user' ? 'primary' : 'secondary'}
                appearance="light"
                size="sm"
                shape="circle"
              >
                {row.source === 'user' ? 'User' : 'Seed'}
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <code className="truncate">{row.spec_key}</code>
              <span className="flex items-center gap-1.5">
                Unit
                {mode === 'edit' && draft ? (
                  <Input
                    value={draft.unit}
                    onChange={(event) =>
                      setDraft((d) => ({ ...d, unit: event.target.value }))
                    }
                    className="h-7 w-20"
                    placeholder="e.g. mm"
                    aria-label="Unit"
                    maxLength={20}
                  />
                ) : (
                  <span>{row.unit || 'None'}</span>
                )}
              </span>
            </div>
          </div>

          {/* An edit session states ONE intent: Save or Cancel. Nav and Delete act on
              the record as it is STORED, and offering them over a screen of unsaved
              changes is offering to act on something nobody is reading (same rule
              SalesAgentDetail's header follows) - so both hide while editing. */}
          <DetailActions
            pagerNode={mode === 'edit' ? null : pagerNode}
            actions={mode === 'edit' ? [] : actions}
            pendingAction={pending}
            primary={primary}
            gearLabel="Specification options"
          />
        </div>
      </CardHeader>
    </Card>
  );
}

export default SpecKeyRecordCard;
