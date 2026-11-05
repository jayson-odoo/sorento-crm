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
import { comboShape, fitReason, needsText } from '@/lib/dealer-kit/combo-slots';
import type { ComboPartOption } from '@/app/(auth)/portal/lib/price-tag-request-service';
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
  /** The combo's parts: with them each template shows what it needs from this combo and one
   *  that does not fit is listed disabled with the reason (PRICETAG-COMBO-RENDER K6). */
  parts?: Pick<ComboPartOption, 'choice_group' | 'is_upgrade'>[];
}

export function ComboTemplatesPicker({
  idPrefix,
  value,
  defaultId,
  onChange,
  selectedOptions,
  disabled,
  parts,
}: Props) {
  const templateOptions = usePriceTagTemplateOptions(true);
  const options = useMemo(() => {
    const shape = parts && parts.length > 0 ? comboShape(parts) : null;
    return (templateOptions.data ?? []).map((template) => {
      const size =
        template.print_size.width_mm && template.print_size.height_mm
          ? `${template.print_size.width_mm} x ${template.print_size.height_mm} mm`
          : '';
      const needs = shape && template.needs ? template.needs : null;
      const reason = shape && needs ? fitReason(needs, shape) : null;
      return {
        value: template.id,
        label: template.name,
        description:
          reason ??
          ((shape && needs ? [size, needsText(needs, shape)].filter(Boolean).join('. ') : size) || undefined),
        disabled: reason ? true : undefined,
        badgeText: reason ? 'Does not fit' : undefined,
      };
    });
  }, [templateOptions.data, parts]);
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
