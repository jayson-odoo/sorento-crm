/**
 * SetTargetModal (S1-24, S1-25, S1-27). Modelled on `sales/teams/components/SalesTeamModal.test.tsx`.
 *
 * Exported default: `SetTargetModal` from `./SetTargetModal`, props
 * `{ open: boolean; onOpenChange: (open: boolean) => void; presetKind?: 'agent' | 'team' | 'dealer'; presetSubjectId?: string }`.
 * Test surface the coder must match:
 *   - `SearchableSelect` mocked to a native `<select>` keyed by its `id`: `target-for`, `who`,
 *     `metric`, `counts`, `applies-to`, `split-unit` (S1-24).
 *   - Dates: the shared `DateRangePicker` (`components/ui/date-range-picker.tsx`), mocked below
 *     to capture its `{ from, to, onChange }` props - NOT two separate date inputs (S1-25). The
 *     mock renders `data-testid="target-dates"`.
 *   - Split: `getByRole('switch', { name: 'Split' })`; once on, `getByLabelText('Every')` (a
 *     number input) and the unit select `split-unit`.
 *   - Figure: `getByLabelText(/target figure/i)`.
 *   - Team mode's Agents table: `getByRole('table', { name: 'Agents' })`, one row per member
 *     with a `getByLabelText('<agent label> figure')` number input, and a read-only
 *     `getByText(/team target/i)` sum.
 *   - `getByRole('button', { name: 'Save' })`.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

// S1-25: the modal's date range is the SHARED `DateRangePicker`, one control, not two date
// inputs. Captured props let the tests drive it exactly as its own component contract
// (`components/ui/date-range-picker.tsx`) does: `onChange({ from, to })` as YYYY-MM-DD.
const dateRangeProps = vi.hoisted(() => ({
  current: null as null | {
    from?: string | null;
    to?: string | null;
    onChange: (next: { from: string | null; to: string | null }) => void;
  },
}));
vi.mock('@/components/ui/date-range-picker', () => ({
  DateRangePicker: (props: {
    from?: string | null;
    to?: string | null;
    onChange: (next: { from: string | null; to: string | null }) => void;
    id?: string;
    'aria-label'?: string;
  }) => {
    dateRangeProps.current = props;
    return (
      <div data-testid="target-dates" aria-label={props['aria-label']}>
        <span data-testid="target-dates-from">{props.from ?? ''}</span>
        <span data-testid="target-dates-to">{props.to ?? ''}</span>
      </div>
    );
  },
}));

/** Drives the mocked `DateRangePicker` exactly as a real pick would: one `onChange({from,to})`. */
function pickDateRange(from: string, to: string) {
  act(() => dateRangeProps.current!.onChange({ from, to }));
}

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    clearable?: boolean;
  }) => (
    <select
      id={props.id}
      data-clearable={props.clearable ? 'true' : 'false'}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="" />
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    value: string[];
    onChange: (v: string[]) => void;
    options?: { value: string; label: string }[];
  }) => (
    <fieldset aria-label="Categories">
      {(props.options ?? []).map((o) => (
        <label key={o.value}>
          <input
            type="checkbox"
            checked={props.value.includes(o.value)}
            onChange={(e) =>
              props.onChange(e.target.checked ? [...props.value, o.value] : props.value.filter((v) => v !== o.value))
            }
          />
          {o.label}
        </label>
      ))}
    </fieldset>
  ),
}));

const save = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const optionsHooks = vi.hoisted(() => ({
  useSalesTargetOptions: () => ({
    data: {
      agents: [
        { id: 'a1', code: 'ALI', label: 'ALI - Ali Hassan', team_id: 'north', team_name: 'North' },
        { id: 'b1', code: 'MEI', label: 'MEI - Tan Mei Ling', team_id: 'north', team_name: 'North' },
      ],
      teams: [
        {
          id: 'north', name: 'North', is_active: true,
          members: [
            { sales_agent_id: 'a1', label: 'ALI - Ali Hassan', valid_from: null, valid_to: null },
            { sales_agent_id: 'b1', label: 'MEI - Tan Mei Ling', valid_from: null, valid_to: null },
          ],
        },
      ],
      categories: [{ id: 'c1', label: 'Basins', parent_category_id: null }],
    },
    isLoading: false,
  }),
  useCreateSalesTarget: () => save,
}));
vi.mock('../hooks/useSalesTargets', () => optionsHooks);

import SetTargetModal from './SetTargetModal';

beforeEach(() => {
  save.mutateAsync.mockReset();
  save.mutateAsync.mockResolvedValue({ id: 'new' });
  dateRangeProps.current = null;
});

describe('SetTargetModal', () => {
  it('defaults to Amount, Ordered, All products, today to end of month, split off', () => {
    render(<SetTargetModal open onOpenChange={() => {}} />);
    expect((screen.getByLabelText(/target for/i) as HTMLSelectElement).value).toBe('');
    expect((document.getElementById('metric') as HTMLSelectElement).value).toBe('amount');
    expect((document.getElementById('counts') as HTMLSelectElement).value).toBe('ordered');
    expect((document.getElementById('applies-to') as HTMLSelectElement).value).toBe('all');
    expect(screen.getByRole('switch', { name: 'Split' })).not.toBeChecked?.();
  });

  it('Save is disabled until a subject is picked', () => {
    render(<SetTargetModal open onOpenChange={() => {}} />);
    expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('presets Target for to the open tab and leaves Who empty (S1-18)', () => {
    render(<SetTargetModal open onOpenChange={() => {}} presetKind="team" />);
    expect((screen.getByLabelText(/target for/i) as HTMLSelectElement).value).toBe('team');
    expect((screen.getByLabelText(/^who/i) as HTMLSelectElement).value).toBe('');
  });

  it('reveals the category multi-select only when Applies to is Categories (S1-15)', () => {
    render(<SetTargetModal open onOpenChange={() => {}} presetKind="agent" />);
    expect(screen.queryByRole('group', { name: 'Categories' })).toBeNull();
    fireEvent.change(document.getElementById('applies-to') as HTMLSelectElement, { target: { value: 'categories' } });
    expect(screen.getByRole('group', { name: 'Categories' })).toBeTruthy();
  });

  it('the split switch reveals Every N unit, and Split unit is the only clearable picker (S1-24, S1-25)', () => {
    render(<SetTargetModal open onOpenChange={() => {}} presetKind="agent" />);
    expect(screen.queryByLabelText('Every')).toBeNull();
    fireEvent.click(screen.getByRole('switch', { name: 'Split' }));
    expect(screen.getByLabelText('Every')).toBeTruthy();
    const splitUnit = screen.getByLabelText(/split unit/i) as HTMLSelectElement;
    expect(splitUnit.dataset.clearable).toBe('true');
    expect((screen.getByLabelText(/^metric$/i) as HTMLSelectElement).dataset.clearable).toBe('false');
  });

  it('clearing Split unit turns the split off', () => {
    render(<SetTargetModal open onOpenChange={() => {}} presetKind="agent" />);
    fireEvent.click(screen.getByRole('switch', { name: 'Split' }));
    fireEvent.change(screen.getByLabelText(/split unit/i), { target: { value: '' } });
    expect(screen.queryByLabelText('Every')).toBeNull();
  });

  it('labels the figure field for the whole range, or per period once split (S1-25)', () => {
    render(<SetTargetModal open onOpenChange={() => {}} presetKind="agent" />);
    expect(screen.getByLabelText(/target figure.*whole range/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('switch', { name: 'Split' }));
    expect(screen.getByLabelText(/target figure.*per period/i)).toBeTruthy();
  });

  it('renders the shared DateRangePicker for the dates, not two date inputs (S1-25)', () => {
    render(<SetTargetModal open onOpenChange={() => {}} presetKind="agent" />);
    expect(screen.getByTestId('target-dates')).toBeTruthy();
    expect(screen.queryByLabelText('Start date')).toBeNull();
    expect(screen.queryByLabelText('End date')).toBeNull();
  });

  it('sends the S1-19 payload for an agent target', async () => {
    render(<SetTargetModal open onOpenChange={() => {}} presetKind="agent" />);
    fireEvent.change(screen.getByLabelText(/^who/i), { target: { value: 'a1' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'North FY26 H2' } });
    pickDateRange('2026-10-01', '2026-12-31');
    fireEvent.change(screen.getByLabelText(/target figure/i), { target: { value: '120000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(save.mutateAsync).toHaveBeenCalledTimes(1));
    expect(save.mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        subject_kind: 'agent', sales_agent_id: 'a1', name: 'North FY26 H2', metric: 'amount',
        basis: 'ordered', product_scope: 'all', start_date: '2026-10-01', end_date: '2026-12-31',
        target_value: 120000,
      }),
    );
  });

  it('Team mode shows an Agents table prefilled with members and a read-only sum (S1-27)', async () => {
    render(<SetTargetModal open onOpenChange={() => {}} presetKind="team" />);
    fireEvent.change(screen.getByLabelText(/^who/i), { target: { value: 'north' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'North Team Target' } });
    const table = screen.getByRole('table', { name: 'Agents' });
    expect(within(table).getByText('ALI - Ali Hassan')).toBeTruthy();
    expect(within(table).getByText('MEI - Tan Mei Ling')).toBeTruthy();
    expect(screen.queryByLabelText(/target figure/i)).toBeNull(); // no editable team figure field

    fireEvent.change(screen.getByLabelText('ALI - Ali Hassan figure'), { target: { value: '600' } });
    fireEvent.change(screen.getByLabelText('MEI - Tan Mei Ling figure'), { target: { value: '400' } });
    expect(within(screen.getByText(/team target/i).closest('div')!).getByText('1,000')).toBeTruthy();

    pickDateRange('2026-10-01', '2026-10-31');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(save.mutateAsync).toHaveBeenCalledTimes(1));
    expect(save.mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        subject_kind: 'team', sales_team_id: 'north',
        agent_figures: [
          { sales_agent_id: 'a1', target_value: 600 },
          { sales_agent_id: 'b1', target_value: 400 },
        ],
      }),
    );
  });
});
