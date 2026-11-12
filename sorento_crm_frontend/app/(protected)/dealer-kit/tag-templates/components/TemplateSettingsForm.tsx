'use client';

/**
 * The tag template's settings, ONE form for create and edit (TAG-TEMPLATE-DUPLICATE item 7,
 * owner rule 28 Oct: create and edit forms are identical and use the same component).
 *
 * Rendered by "New tag template" (`TagTemplateDialog`) and the editor's "Template settings"
 * (`TemplateSettingsDialog`): Name, Family, Price type, Width, Height, in that order, with the
 * same labels and the same validation (`templateSettingsErrors`). The host owns the values and
 * what Save does. The one difference a host may pass is the family list: an existing template
 * stays a price tag or a spec sheet page, so its Settings offers only its own kind.
 *
 * The size here and the editor's left TAG SIZE panel are the same value
 * (`template.doc.width_mm/height_mm`), written through the same draft resize, so the two are
 * linked both ways and cannot disagree.
 */
import { useId } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { numberFieldError } from '@/lib/number-field';
import {
  TEMPLATE_PRICE_TYPE_OPTIONS,
  type TemplatePriceType,
} from '@/lib/dealer-kit/template-price-type';
import type { TagTemplateFamily } from '@/lib/dealer-kit/tag-template-types';

export const TEMPLATE_MIN_MM = 10;

/** The form's values while editing; a size is null while its box is empty. */
export interface TemplateSettingsDraft {
  name: string;
  family: TagTemplateFamily;
  price_type: TemplatePriceType | null;
  width_mm: number | null;
  height_mm: number | null;
}

/** One rule set for both hosts: a name, and a size of at least 10 mm each way. */
export function templateSettingsErrors(draft: TemplateSettingsDraft) {
  return {
    name: draft.name.trim().length === 0,
    width_mm: numberFieldError(draft.width_mm, { min: TEMPLATE_MIN_MM }),
    height_mm: numberFieldError(draft.height_mm, { min: TEMPLATE_MIN_MM }),
  };
}

export function templateSettingsValid(draft: TemplateSettingsDraft): boolean {
  const errors = templateSettingsErrors(draft);
  return !errors.name && !errors.width_mm && !errors.height_mm;
}

interface TemplateSettingsFormProps {
  value: TemplateSettingsDraft;
  onChange: (next: TemplateSettingsDraft) => void;
  familyOptions: { value: string; label: string }[];
  /** True once Save was pressed: size errors show from then on. */
  showErrors: boolean;
  autoFocusName?: boolean;
}

export function TemplateSettingsForm({
  value,
  onChange,
  familyOptions,
  showErrors,
  autoFocusName = false,
}: TemplateSettingsFormProps) {
  const id = useId();
  const set = <K extends keyof TemplateSettingsDraft>(key: K, next: TemplateSettingsDraft[K]) =>
    onChange({ ...value, [key]: next });
  const errors = templateSettingsErrors(value);

  return (
    <div className="flex flex-col gap-4" data-testid="template-settings-form">
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${id}-name`} data-field-label>
          Name
        </Label>
        <Input
          id={`${id}-name`}
          value={value.name}
          onChange={(e) => set('name', e.target.value)}
          autoFocus={autoFocusName}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-2">
          <Label id={`${id}-family`} data-field-label>
            Family
          </Label>
          <SearchableSelect
            aria-label="Family"
            value={value.family}
            onChange={(v: string) => set('family', v as TagTemplateFamily)}
            options={familyOptions}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <Label id={`${id}-price-type`} data-field-label>
            Price type
          </Label>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            aria-labelledby={`${id}-price-type`}
            value={value.price_type ?? ''}
            onValueChange={(next) => set('price_type', (next || null) as TemplatePriceType | null)}
            className="flex-wrap"
          >
            {TEMPLATE_PRICE_TYPE_OPTIONS.map((option) => (
              <ToggleGroupItem key={option.value} value={option.value}>
                {option.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-width`} data-field-label>
            Width (mm)
          </Label>
          <NumberInput
            id={`${id}-width`}
            value={value.width_mm}
            min={TEMPLATE_MIN_MM}
            onValueChange={(next) => set('width_mm', next)}
            error={showErrors ? errors.width_mm : undefined}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-height`} data-field-label>
            Height (mm)
          </Label>
          <NumberInput
            id={`${id}-height`}
            value={value.height_mm}
            min={TEMPLATE_MIN_MM}
            onValueChange={(next) => set('height_mm', next)}
            error={showErrors ? errors.height_mm : undefined}
          />
        </div>
      </div>
    </div>
  );
}
