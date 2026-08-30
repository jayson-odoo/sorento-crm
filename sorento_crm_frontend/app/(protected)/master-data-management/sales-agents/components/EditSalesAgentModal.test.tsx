/**
 * EditSalesAgentModal - the two annotation fields, and nothing else.
 *
 * What this pins:
 * - the demand-class select offers EXACTLY the two classes the policy can weigh,
 *    plus a clear (unset is a real answer, and the backend refuses a third word);
 * - saving sends `{ person_label, demand_class }` with `null` for "not set", so a
 *    cleared class is unset rather than left as it was;
 * - the agent code is shown, not editable: it is what documents state.
 *
 * SearchableSelect is stubbed to a native <select> (the real one is a Radix popover +
 * cmdk list, which jsdom cannot drive), and the stub records `clearable` so the
 * clearable requirement is asserted rather than assumed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const selectProps = vi.hoisted(() => ({ current: null as Record<string, unknown> | null }));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    clearable?: boolean;
  }) => {
    // Two selects live in this modal now: the static demand class, and the
    // contact picker, which is server-searched and so has no `options` at all.
    const isStatic = Array.isArray(props.options);
    if (isStatic) selectProps.current = props as unknown as Record<string, unknown>;
    return (
      <select
        aria-label={isStatic ? 'Demand class' : 'Linked portal contact'}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
      >
        <option value="">{props.placeholder ?? ''}</option>
        {(props.options ?? []).map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

import { EditSalesAgentModal } from './EditSalesAgentModal';
import type { SalesAgent } from '../types/salesAgent.types';

const AGENT: SalesAgent = {
  id: 'agent-1',
  sales_agent: 'SEAN III',
  description: null,
  is_active: true,
  internal_note: null,
  follow_up: false,
  person_label: 'Sean',
  demand_class: 'project',
  location_group: 'BB',
  contact_id: null,
  contact_name: null,
  source: 'import',
  created_at: '2026-08-01T00:00:00',
  updated_at: null,
};

function renderModal(over: Partial<React.ComponentProps<typeof EditSalesAgentModal>> = {}) {
  const props: React.ComponentProps<typeof EditSalesAgentModal> = {
    open: true,
    onOpenChange: vi.fn(),
    agent: AGENT,
    isSaving: false,
    onSave: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
  render(<EditSalesAgentModal {...props} />);
  return props;
}

beforeEach(() => {
  selectProps.current = null;
});

describe('EditSalesAgentModal', () => {
  it('offers exactly the two demand classes plus a clear', () => {
    renderModal();

    expect(selectProps.current?.options).toEqual([
      { value: 'project', label: 'Project' },
      { value: 'retail', label: 'Retail' },
    ]);
    expect(selectProps.current?.clearable).toBe(true);
  });

  it('shows the agent code and prefills every field', () => {
    renderModal();

    expect(screen.getByText('Edit SEAN III')).toBeInTheDocument();
    expect(screen.getByLabelText('Person')).toHaveValue('Sean');
    expect(screen.getByLabelText('Demand class')).toHaveValue('project');
    expect(screen.getByLabelText('Location group')).toHaveValue('BB');
  });

  it('saves the edited label, class and location group', async () => {
    const props = renderModal();

    fireEvent.change(screen.getByLabelText('Person'), { target: { value: 'Sean Lim' } });
    fireEvent.change(screen.getByLabelText('Demand class'), { target: { value: 'retail' } });
    fireEvent.change(screen.getByLabelText('Location group'), { target: { value: '  hp  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(props.onSave).toHaveBeenCalledWith({
        person_label: 'Sean Lim',
        demand_class: 'retail',
        location_group: 'HP',
        contact_id: null,
      }),
    );
  });

  it('clearing the class sends null rather than an empty string', async () => {
    const props = renderModal();

    fireEvent.change(screen.getByLabelText('Demand class'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(props.onSave).toHaveBeenCalledWith({
        person_label: 'Sean',
        demand_class: null,
        location_group: 'BB',
        contact_id: null,
      }),
    );
  });

  it('clearing the location group sends null rather than an empty string', async () => {
    const props = renderModal();

    fireEvent.change(screen.getByLabelText('Location group'), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(props.onSave).toHaveBeenCalledWith({
        person_label: 'Sean',
        demand_class: 'project',
        location_group: null,
        contact_id: null,
      }),
    );
  });

  it('a blank person is sent as null', async () => {
    const props = renderModal({
      agent: { ...AGENT, person_label: null, demand_class: null, location_group: null },
    });

    fireEvent.change(screen.getByLabelText('Person'), { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(props.onSave).toHaveBeenCalledWith({
        person_label: null,
        demand_class: null,
        location_group: null,
        contact_id: null,
      }),
    );
  });

  it('Save is disabled while a save is in flight', () => {
    renderModal({ isSaving: true });
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('a refused save is swallowed, and the modal stays open on the edited values', async () => {
    // The mutation hook has already toasted the message; an uncaught rejection here would
    // surface as an unhandled promise rejection and tell the user nothing extra.
    const onUnhandled = vi.fn();
    window.addEventListener('unhandledrejection', onUnhandled);

    const props = renderModal({
      onSave: vi.fn().mockRejectedValue(new Error("'dealer' is not a demand class")),
      onOpenChange: vi.fn(),
    });

    fireEvent.change(screen.getByLabelText('Person'), { target: { value: 'Sean Lim' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(props.onSave).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));

    expect(onUnhandled).not.toHaveBeenCalled();
    expect(props.onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Person')).toHaveValue('Sean Lim');

    window.removeEventListener('unhandledrejection', onUnhandled);
  });
});
