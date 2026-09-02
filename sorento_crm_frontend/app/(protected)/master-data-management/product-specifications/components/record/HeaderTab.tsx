'use client';

import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import type { SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

/** One labelled control. The label is the only chrome a field needs, present in
 *  both view and edit so a field's identity never moves between the two (B.2). */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

export interface HeaderTabProps {
  row: SpecRegistryKey;
  mode: 'view' | 'edit';
  /** Null in view mode - the tab reads straight off `row` then. */
  draft: SpecKeyDraft | null;
  setDraft: (updater: (draft: SpecKeyDraft) => SpecKeyDraft) => void;
}

/**
 * The specification's own identity fields (B.2, D15b): Label, Unit, Active, and for
 * a numeric key the cap moved here from Values and words. First in the tab order -
 * a reader lands here to change what the specification IS before touching what it
 * says or how it is read.
 */
export function HeaderTab({ row, mode, draft, setDraft }: HeaderTabProps) {
  const isNumeric = row.data_type === 'numeric';

  return (
    <div className="flex max-w-xl flex-col gap-4">
      <Field label="Label">
        {mode === 'edit' && draft ? (
          <Input
            value={draft.label}
            onChange={(event) => setDraft((d) => ({ ...d, label: event.target.value }))}
            className="h-8"
            aria-label="Label"
            maxLength={100}
          />
        ) : (
          <span className="text-sm">{row.label}</span>
        )}
      </Field>

      <Field label="Unit">
        {mode === 'edit' && draft ? (
          <Input
            value={draft.unit}
            onChange={(event) => setDraft((d) => ({ ...d, unit: event.target.value }))}
            className="h-8 w-40"
            placeholder="e.g. mm"
            aria-label="Unit"
            maxLength={20}
          />
        ) : (
          <span className="text-sm">{row.unit || 'None'}</span>
        )}
      </Field>

      <Field label="Active">
        <Switch
          size="sm"
          aria-label="Active"
          checked={mode === 'edit' && draft ? draft.isActive : row.is_active}
          disabled={mode !== 'edit' || !draft}
          onCheckedChange={(checked) => setDraft((d) => ({ ...d, isActive: checked }))}
        />
      </Field>

      {isNumeric && (
        <Field label={`Ignore values above${row.unit ? ` (${row.unit})` : ''}`}>
          {mode === 'edit' && draft ? (
            <Input
              type="number"
              step="1"
              min="0"
              placeholder="no cap"
              className="h-8 w-40"
              value={draft.maxValue}
              onChange={(event) => setDraft((d) => ({ ...d, maxValue: event.target.value }))}
            />
          ) : (
            <span className="text-sm">
              {row.max_value === null || row.max_value === undefined
                ? 'No cap'
                : row.unit
                  ? `${row.max_value} ${row.unit}`
                  : row.max_value}
            </span>
          )}
        </Field>
      )}
    </div>
  );
}

export default HeaderTab;
