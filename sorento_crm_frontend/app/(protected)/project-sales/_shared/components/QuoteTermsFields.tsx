'use client';

import * as React from 'react';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { usePaymentTermOptions } from '../hooks/usePaymentTerms';
import {
  VALIDITY_UNITS,
  formatValidity,
  type QuoteTermsPick,
  type ValidityUnit,
} from '../services/paymentTermService';

/** A change from the fields: the picks plus the text they print as, so a preview and a read view
 *  show the new values before the server answers. */
export type QuoteTermsPatch = QuoteTermsPick & {
  payment_terms?: string | null;
  validity?: string | null;
};

export interface QuoteTermsValues {
  payment_term_id?: string | null;
  payment_terms?: string | null;
  validity_value?: number | null;
  validity_unit?: ValidityUnit | string | null;
  validity?: string | null;
}

const UNIT_OPTIONS: SearchableSelectOption[] = VALIDITY_UNITS.map((unit) => ({
  value: unit.value,
  label: unit.label,
}));

function isUnit(value: unknown): value is ValidityUnit {
  return VALIDITY_UNITS.some((unit) => unit.value === value);
}

/**
 * Payment Terms (a select over the AutoCount-synced terms) and Validity (a number and a unit),
 * for the terms template dialog and the quotation's Terms tab alike (QUOTE-TERMS-SELECT).
 *
 * A legacy free-text value that has no pick behind it stays visible as "Current: ..." under its
 * field and keeps printing until someone picks.
 */
export function QuoteTermsFields({
  values,
  onChange,
  projectId,
  idPrefix,
}: {
  values: QuoteTermsValues;
  onChange: (patch: QuoteTermsPatch) => void;
  /** The quotation form's project; absent in the terms template dialog. */
  projectId?: string;
  idPrefix: string;
}) {
  const terms = usePaymentTermOptions(projectId);
  const termId = values.payment_term_id ?? '';

  const options = React.useMemo<SearchableSelectOption[]>(() => {
    const list: SearchableSelectOption[] = (terms.data ?? []).map((term) => ({
      value: term.id,
      label: term.label,
      searchText: `${term.label} ${term.code}`,
      description: term.description && term.code !== term.label ? term.code : undefined,
    }));
    // A term picked before it was deactivated in AutoCount still shows as picked.
    if (termId && !list.some((option) => option.value === termId)) {
      list.push({ value: termId, label: values.payment_terms || 'Retired term' });
    }
    return list;
  }, [terms.data, termId, values.payment_terms]);

  // What prints, when it is not what the select shows: a legacy text nobody picked over, or one a
  // sync linked to a term whose label reads differently.
  const printedTerms = (values.payment_terms ?? '').trim();
  const pickedLabel = options.find((option) => option.value === termId)?.label ?? '';
  const legacyTerms = printedTerms && printedTerms !== pickedLabel.trim() ? printedTerms : null;

  // The number and the unit are sent as a pair, so a half-typed one stays here until it is whole.
  const [value, setValue] = React.useState<string>(
    values.validity_value != null ? String(values.validity_value) : '',
  );
  const [unit, setUnit] = React.useState<string>(
    isUnit(values.validity_unit) ? values.validity_unit : '',
  );
  React.useEffect(() => {
    setValue(values.validity_value != null ? String(values.validity_value) : '');
    setUnit(isUnit(values.validity_unit) ? values.validity_unit : '');
  }, [values.validity_value, values.validity_unit]);

  const legacyValidity =
    values.validity_value == null && (values.validity ?? '').trim() ? values.validity : null;

  function emitValidity(nextValue: string, nextUnit: string) {
    const number = Number(nextValue);
    // An emptied number clears the validity, whatever the unit says.
    if (!nextValue) {
      if (nextUnit) setUnit('');
      if (values.validity_value != null || values.validity) {
        onChange({ validity_value: null, validity_unit: null, validity: null });
      }
      return;
    }
    if (nextValue && Number.isInteger(number) && number >= 1 && number <= 999 && isUnit(nextUnit)) {
      onChange({
        validity_value: number,
        validity_unit: nextUnit,
        validity: formatValidity(number, nextUnit),
      });
    }
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="min-w-0 space-y-1.5">
        <Label htmlFor={`${idPrefix}-payment-terms`}>Payment Terms</Label>
        <SearchableSelect
          id={`${idPrefix}-payment-terms`}
          value={termId}
          options={options}
          clearable
          loadError={terms.error}
          onRetry={() => void terms.refetch()}
          placeholder="Select payment terms"
          emptyMessage="No AutoCount payment terms synced yet."
          onChange={(next) => {
            const picked = options.find((option) => option.value === next);
            onChange(
              next
                ? { payment_term_id: next, payment_terms: picked?.label ?? null }
                : { payment_term_id: null, payment_terms: null },
            );
          }}
        />
        {legacyTerms && (
          <p className="min-w-0 truncate text-xs text-muted-foreground" title={legacyTerms}>
            Current: {legacyTerms}
          </p>
        )}
      </div>
      <div className="min-w-0 space-y-1.5">
        <Label htmlFor={`${idPrefix}-validity`}>Validity</Label>
        <div className="flex min-w-0 gap-2">
          <Input
            id={`${idPrefix}-validity`}
            type="number"
            inputMode="numeric"
            min={1}
            max={999}
            step={1}
            className="w-24 shrink-0"
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              emitValidity(event.target.value, unit);
            }}
          />
          <SearchableSelect
            id={`${idPrefix}-validity-unit`}
            aria-label="Validity unit"
            className="min-w-0 flex-1"
            value={unit}
            options={UNIT_OPTIONS}
            clearable
            placeholder="Unit"
            onChange={(next) => {
              setUnit(next);
              emitValidity(value, next);
            }}
          />
        </div>
        {legacyValidity && (
          <p className="min-w-0 truncate text-xs text-muted-foreground" title={legacyValidity}>
            Current: {legacyValidity}
          </p>
        )}
      </div>
    </div>
  );
}
