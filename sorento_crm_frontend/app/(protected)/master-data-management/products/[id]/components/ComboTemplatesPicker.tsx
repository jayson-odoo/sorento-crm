'use client';

/**
 * The "Price tag templates" field of a combo (PRICETAG-LPSP): which tag templates the combo
 * prints with, and once two or more are chosen, which one is the default. Shared by the Add
 * combo modal and an existing combo's block, so both read and write the same way.
 */

import { useMemo } from 'react';
import { Label } from '@/components/ui/label';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { usePriceTagTemplateOptions } from '@/app/(protected)/dealer-kit/hooks/useProductTagTemplates';

interface Props {
  /** Prefix for the field ids (one picker per combo on a page). */
  idPrefix: string;
  value: string[];
  defaultId: string;
  onChange: (ids: string[], defaultId: string) => void;
  /** Current links shown while the options load (an existing combo). */
  selectedOptions?: { value: string; label: string; description?: string }[];
  disabled?: boolean;
}

export function ComboTemplatesPicker({
  idPrefix,
  value,
  defaultId,
  onChange,
  selectedOptions,
  disabled,
}: Props) {
  const templateOptions = usePriceTagTemplateOptions(true);
  const options = useMemo(
    () =>
      (templateOptions.data ?? []).map((template) => ({
        value: template.id,
        label: template.name,
        description:
          template.print_size.width_mm && template.print_size.height_mm
            ? `${template.print_size.width_mm} x ${template.print_size.height_mm} mm`
            : undefined,
      })),
    [templateOptions.data],
  );
  // The default is chosen among the linked templates; their names come from the options, or the
  // current links while the options are still loading.
  const defaultOptions = value.flatMap((id) => {
    const found = options.find((o) => o.value === id) ?? selectedOptions?.find((o) => o.value === id);
    return found ? [found] : [];
  });
  return (
    <div className="space-y-1.5">
      <Label htmlFor={`${idPrefix}-templates`}>Price tag templates</Label>
      <SearchableMultiSelect
        id={`${idPrefix}-templates`}
        clearable
        value={value}
        selectedOptions={selectedOptions}
        onChange={(ids) => onChange(ids, ids.includes(defaultId) ? defaultId : '')}
        options={options}
        loadError={templateOptions.error ?? undefined}
        onRetry={() => void templateOptions.refetch()}
        disabled={disabled}
        placeholder="Search templates"
        emptyMessage="No templates."
      />
      {value.length > 1 ? (
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-default-template`}>Default template</Label>
          <SearchableSelect
            id={`${idPrefix}-default-template`}
            clearable
            value={defaultId}
            onChange={(id) => onChange(value, id)}
            options={defaultOptions}
            disabled={disabled}
            placeholder="Default template"
            emptyMessage="No templates."
          />
        </div>
      ) : null}
    </div>
  );
}
