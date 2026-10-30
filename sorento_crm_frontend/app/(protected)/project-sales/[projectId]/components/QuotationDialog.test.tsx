/**
 * QUOTE-UI-POLISH (AC-QUP-1 to AC-QUP-4): the scope dialog's Series starts on the only active
 * series when there is exactly one. The owner, 29 Oct: "for the series, if it is only 1 option
 * then we should default".
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project, ProjectQuotation } from '../../_shared/types/project.types';

type SeriesRow = { id: string; name: string; is_active: boolean; brand_names?: string[] };

let seriesRows: SeriesRow[] | undefined = [];
const create = vi.fn(async () => ({}));
const update = vi.fn(async () => ({}));

vi.mock('../../_shared/hooks/useProjects', () => ({
  useProjectSeries: () => ({ data: seriesRows, error: null, refetch: vi.fn() }),
  useQuotationMutations: () => ({
    create: { mutateAsync: create, isPending: false },
    update: { mutateAsync: update, isPending: false },
  }),
}));

import { QuotationDialog } from './QuotationDialog';

const PROJECT = { id: 'p1', title: 'TRX Zus Coffee' } as Project;
const SOLE: SeriesRow = { id: 's1', name: 'Project', is_active: true, brand_names: ['SORENTO'] };
const RETIRED: SeriesRow = { id: 's0', name: 'Old Range', is_active: false };

function scope(overrides: Partial<ProjectQuotation> = {}): ProjectQuotation {
  return { id: 'q1', scope_label: 'Scope 1', series_id: null, notes: null, ...overrides } as ProjectQuotation;
}

function renderDialog(quotation: ProjectQuotation | null, onSubmit?: (body: unknown) => void) {
  const onDone = vi.fn();
  const view = render(
    <QuotationDialog project={PROJECT} quotation={quotation} onDone={onDone} onSubmit={onSubmit} />,
  );
  return { ...view, onDone };
}

function seriesTrigger() {
  return screen.getByRole('combobox', { name: 'Series' });
}

beforeEach(() => {
  vi.clearAllMocks();
  seriesRows = [SOLE, RETIRED];
});

describe('QuotationDialog series default (QUOTE-UI-POLISH)', () => {
  it('AC-QUP-1: one active series is preselected on a scope that has none', async () => {
    const onSubmit = vi.fn();
    renderDialog(scope(), onSubmit);

    await waitFor(() => expect(seriesTrigger()).toHaveTextContent('Project'));
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ series_id: 's1' });
  });

  it('AC-QUP-1: the project page Add a scope starts on it too, and the create writes it', async () => {
    renderDialog(null);

    await waitFor(() => expect(seriesTrigger()).toHaveTextContent('Project'));
    fireEvent.change(screen.getByRole('textbox', { name: /^Scope/ }), {
      target: { value: 'House Units' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add scope' }));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create.mock.calls[0][0]).toMatchObject({ scope_label: 'House Units', series_id: 's1' });
  });

  it('AC-QUP-1: the series arriving after the dialog opened still preselects it', async () => {
    seriesRows = undefined;
    const { rerender, onDone } = renderDialog(scope());
    expect(seriesTrigger()).toHaveTextContent('No series');

    seriesRows = [SOLE];
    rerender(<QuotationDialog project={PROJECT} quotation={scope()} onDone={onDone} />);

    await waitFor(() => expect(seriesTrigger()).toHaveTextContent('Project'));
  });

  it('AC-QUP-2: a scope that already has a series keeps its own', async () => {
    const onSubmit = vi.fn();
    renderDialog(scope({ series_id: 's0' }), onSubmit);

    await waitFor(() => expect(seriesTrigger()).toHaveTextContent('Old Range'));
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ series_id: 's0' });
  });

  it('AC-QUP-3: two active series preselect nothing', async () => {
    seriesRows = [SOLE, { id: 's2', name: 'Retail', is_active: true }];
    const onSubmit = vi.fn();
    renderDialog(scope(), onSubmit);

    expect(seriesTrigger()).toHaveTextContent('No series');
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ series_id: null });
  });

  it('AC-QUP-4: clearing the preselected series sticks and saves no series', async () => {
    const onSubmit = vi.fn();
    renderDialog(scope(), onSubmit);

    await waitFor(() => expect(seriesTrigger()).toHaveTextContent('Project'));
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Clear selection' }));
    await waitFor(() => expect(seriesTrigger()).toHaveTextContent('No series'));

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ series_id: null });
  });
});
