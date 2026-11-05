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
import type { LinkDefaults } from '@/app/(protected)/dealer-kit/services/productTagTemplateService';
import {
  TEMPLATE_PRICE_TYPE_LABEL,
  templateFitsLine,
  type LinePriceType,
} from '@/lib/dealer-kit/template-price-type';

interface Props {
  /** Prefix for the field ids (one picker per combo on a page). */
  idPrefix: string;
  value: string[];
  /** One default LP and one default SP template ('' = none chosen). */
  defaultListId?: string;
  defaultSellingId?: string;
  onChange: (ids: string[], defaults: LinkDefaults) => void;
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
  defaultListId = '',
  defaultSellingId = '',
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
      const typeText = template.price_type ? TEMPLATE_PRICE_TYPE_LABEL[template.price_type] : 'Not set';
      return {
        value: template.id,
        label: template.name,
        description:
          reason ??
          ((shape && needs ? [size, needsText(needs, shape)].filter(Boolean).join('. ') : size) || undefined),
        disabled: reason ? true : undefined,
        badgeText: reason ? `${typeText} / Does not fit` : typeText,
      };
    });
  }, [templateOptions.data, parts]);
  const typeById = useMemo(
    () => new Map((templateOptions.data ?? []).map((template) => [template.id, template.price_type ?? null])),
    [templateOptions.data],
  );
  // The default is chosen among the linked templates; their names come from the options, or the
  // current links while the options are still loading.
  const defaultOptions = (kind: LinePriceType) =>
    value.flatMap((id) => {
      const found = options.find((o) => o.value === id) ?? selectedOptions?.find((o) => o.value === id);
      return found && templateFitsLine(typeById.get(id) ?? null, kind) ? [{ value: found.value, label: found.label }] : [];
    });
  const defaults: LinkDefaults = { list: defaultListId, selling: defaultSellingId };
  return (
    <div className="space-y-1.5">
      <Label htmlFor={`${idPrefix}-templates`}>Price tag templates</Label>
      <SearchableMultiSelect
        id={`${idPrefix}-templates`}
        clearable
        value={value}
        selectedOptions={selectedOptions?.map((o) => ({
          ...o,
          badgeText: (o as { badgeText?: string }).badgeText ?? options.find((x) => x.value === o.value)?.badgeText,
        }))}
        onChange={(ids) =>
          onChange(ids, {
            list: ids.includes(defaults.list) ? defaults.list : '',
            selling: ids.includes(defaults.selling) ? defaults.selling : '',
          })
        }
        options={options}
        loadError={templateOptions.error ?? undefined}
        onRetry={() => void templateOptions.refetch()}
        disabled={disabled}
        placeholder="Search templates"
        emptyMessage="No templates."
      />
      {value.length > 1 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              ['list', 'Default LP template', defaultListId],
              ['selling', 'Default SP template', defaultSellingId],
            ] as const
          ).map(([kind, label, current]) => (
            <div key={kind} className="min-w-0 space-y-1.5">
              <Label htmlFor={`${idPrefix}-default-${kind}`}>{label}</Label>
              <SearchableSelect
                id={`${idPrefix}-default-${kind}`}
                aria-label={label}
                clearable
                value={current}
                onChange={(id) => onChange(value, { ...defaults, [kind === 'list' ? 'list' : 'selling']: id })}
                options={defaultOptions(kind)}
                disabled={disabled}
                placeholder={label}
                emptyMessage="No templates."
              />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
