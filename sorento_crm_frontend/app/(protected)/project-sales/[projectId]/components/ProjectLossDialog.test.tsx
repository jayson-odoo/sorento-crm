/**
 * PROJECT-OUTCOME-SINGLE FE1: the Mark lost reason dialog.
 *
 * Props assumed by these tests (the contract names the file, not the props):
 * { projectId, toStatusId, onDone }. The dialog reads the configured reasons itself and
 * saves through useChangeProjectStatus, so the project page and the pipeline board's Lost
 * column drop can both mount it with the same three props.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn();
Element.prototype.setPointerCapture = vi.fn();
Element.prototype.releasePointerCapture = vi.fn();

const mutate = vi.fn();
let reasons: { value: string; label: string }[] = [];
let pending = false;
vi.mock('../../_shared/hooks/useProjects', () => ({
  useChangeProjectStatus: () => ({ mutate, isPending: pending }),
  useQuotationLossReasons: () => ({ data: reasons, isLoading: false }),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    id,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    id?: string;
  }) => (
    <select
      id={id}
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { ProjectLossDialog } from './ProjectLossDialog';

const onDone = vi.fn();

function renderDialog() {
  return render(<ProjectLossDialog projectId="p1" toStatusId="s-lost" onDone={onDone} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  pending = false;
  reasons = [
    { value: 'price', label: 'Price' },
    { value: 'lead_time', label: 'Lead time' },
  ];
});

describe('ProjectLossDialog', () => {
  it('keeps Save disabled until a reason is picked', async () => {
    renderDialog();

    const save = await screen.findByRole('button', { name: 'Save' });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'lead_time' } });
    await waitFor(() => expect(save).toBeEnabled());
  });

  it('lists the configured reasons by label', async () => {
    renderDialog();

    expect(await screen.findByRole('option', { name: 'Price' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Lead time' })).toBeInTheDocument();
  });

  it('Save calls the status change with the loss reason', async () => {
    renderDialog();
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'price' } });
    const save = screen.getByRole('button', { name: 'Save' });
    await waitFor(() => expect(save).toBeEnabled());

    fireEvent.click(save);

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      projectId: 'p1',
      toStatusId: 's-lost',
      lossReason: 'price',
    });
  });

  it('Cancel closes without a move', async () => {
    renderDialog();

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

    expect(onDone).toHaveBeenCalled();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('disables Save while the move is in flight', async () => {
    pending = true;
    renderDialog();
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'price' } });

    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });
});
