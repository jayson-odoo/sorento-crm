/**
 * Test stand-in for `SearchableMultiSelect` (PRICETAG-MULTI-ADD round 3), used through
 * `vi.mock('@/components/common/SearchableMultiSelect')` by the price tag form and table suites.
 *
 * Two jobs, told apart by `renderTrigger`, which only the Item cell passes:
 * - the Item cell becomes a native select labelled with its placeholder. Picking an option calls
 *   `onChange([...value, picked])`, which is exactly what one row click or tick does in the real
 *   list, so the test goes through the real pick path (`addPickedItems` / `handleItemSelect`);
 * - every other multi-select (the Alternatives picker) stays an inert multi select.
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

interface StandInOption {
  value: string;
  label: string;
  disabled?: boolean;
  badgeText?: string;
}

export interface StandInProps {
  value: string[];
  disabled?: boolean;
  onChange?: (next: string[]) => void;
  fetchOptions?: (query: string) => Promise<StandInOption[]>;
  renderOption?: (option: StandInOption) => React.ReactNode;
  renderTrigger?: (state: {
    selected: StandInOption[];
    open: boolean;
    disabled: boolean;
  }) => React.ReactNode;
}

export const ITEM_CELL_LABEL = 'Search a set or product...';

/** What the option reads as: production's own renderOption text when it passes one (the code and
 *  its hints), else the option's own label and badge. Nothing is worked out here. */
function optionText(
  o: StandInOption,
  renderOption?: StandInProps['renderOption'],
): string {
  if (!renderOption) return [o.label, o.badgeText].filter(Boolean).join(' - ');
  const holder = document.createElement('div');
  holder.innerHTML = renderToStaticMarkup(<>{renderOption(o)}</>);
  return (holder.textContent ?? '').replace(/\s+/g, ' ').trim();
}

export function ItemCellStandIn({
  value,
  fetchOptions,
  onChange,
  renderTrigger,
  renderOption,
}: StandInProps) {
  const [options, setOptions] = React.useState<StandInOption[]>([]);
  React.useEffect(() => {
    if (fetchOptions) void fetchOptions('').then(setOptions);
    // The real list fetches on open and on each search, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Shows what this cell picked while that item is still on the request, so a test can read
  // the pick back; once the line is cleared or removed the cell is empty again.
  const [picked, setPicked] = React.useState('');
  const shown = value.includes(picked) ? picked : '';
  return (
    <>
      {/* The closed cell's own look (the line's item name), hidden from role queries so the
          native select below stays the one control a test drives. */}
      <div aria-hidden>
        {/* Open, so the cell's open watcher marks what is on the request, as production does on open. */}
        {renderTrigger?.({ selected: [], open: true, disabled: false })}
      </div>
      <select
        aria-label={ITEM_CELL_LABEL}
        value={shown}
        onChange={(e) => {
          if (!e.target.value) return;
          setPicked(e.target.value);
          onChange?.([...value, e.target.value]);
        }}
      >
        <option value="">{ITEM_CELL_LABEL}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {optionText(o, renderOption)}
          </option>
        ))}
      </select>
    </>
  );
}

export function SearchableMultiSelect(props: StandInProps) {
  if (props.renderTrigger) return <ItemCellStandIn {...props} />;
  return (
    <select
      multiple
      aria-label="Alternatives"
      disabled={props.disabled}
      value={props.value ?? []}
      onChange={() => {}}
    />
  );
}
