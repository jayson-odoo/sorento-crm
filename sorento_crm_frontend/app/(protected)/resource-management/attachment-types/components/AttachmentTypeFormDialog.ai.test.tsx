/**
 * AttachmentTypeFormDialog - "Escalate to" (AGENTIC-KNOWLEDGE P1, AC-K3) after DOC-ACCESS-SIMPLE.
 *
 * DAS-FE-6: the "AI can read" select is gone (who reads a type is ticked on the Document Access
 * page now); create and update no longer send `ai_audience`. "Escalate to" stays: it defaults to
 * no team, reloads the saved team by NAME (AC-K20, no UUID), and sends `ai_escalate_team_id`.
 *
 * The team list is mocked at the lowest shared layer (`teamService.getTeams`) and the dialog is
 * rendered inside a QueryClientProvider, so the test holds whichever hook the form picks to read
 * teams. The selects are located by their visible label, not by position.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const hooks = vi.hoisted(() => ({
  createAsync: vi.fn().mockResolvedValue({}),
  updateAsync: vi.fn().mockResolvedValue({}),
  useAttachmentType: vi.fn(),
  getTeams: vi.fn(),
}));

vi.mock('../hooks/useAttachmentTypes', () => ({
  useCreateAttachmentType: () => ({ mutateAsync: hooks.createAsync, isPending: false }),
  useUpdateAttachmentType: () => ({ mutateAsync: hooks.updateAsync, isPending: false }),
  useAttachmentType: (...a: unknown[]) => hooks.useAttachmentType(...a),
}));

vi.mock('../../attachments/hooks/useAttachments', () => ({
  useDirectoryTree: () => ({ data: [], isLoading: false }),
}));

vi.mock('@/app/(protected)/user-management/teams/services/teamService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/app/(protected)/user-management/teams/services/teamService')>()),
  getTeams: (...a: unknown[]) => hooks.getTeams(...a),
}));

vi.mock('@/app/providers/CompanyProvider', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/app/providers/CompanyProvider')>()),
  useCompany: () => ({ activeCompany: { id: 'company-1', name: 'Sorento' } }),
}));

import AttachmentTypeFormDialog from './AttachmentTypeFormDialog';

const TEAMS = [
  { id: 'team-hr', name: 'HR' },
  { id: 'team-sales', name: 'Sales Support' },
];

function savedType(over: Record<string, unknown> = {}) {
  return {
    id: 'type-1',
    type_name: 'Employee Handbook',
    description: null,
    allowed_extensions: 'pdf,docx',
    max_file_size_mb: 10,
    max_count_per_entity: null,
    supports_field_linkage: false,
    is_certificate: false,
    max_validity_months: null,
    created_at: new Date('2026-01-01'),
    ai_read_staff: true,
    ai_read_codes: ['dealer'],
    ai_escalate_team_id: 'team-hr',
    ai_escalate_team_name: 'HR',
    ...over,
  };
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  hooks.useAttachmentType.mockReturnValue({ data: undefined, isLoading: false });
  hooks.getTeams.mockResolvedValue(TEAMS);
});

function renderDialog(props: { attachmentTypeId?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AttachmentTypeFormDialog open onOpenChange={vi.fn()} {...props} />
    </QueryClientProvider>,
  );
}

/** The form item holding `label`: the nearest ancestor of the label that also holds a combobox. */
function itemOf(label: RegExp | string): HTMLElement {
  let node: HTMLElement | null = screen.getByText(label);
  while (node && !node.querySelector('[role="combobox"]')) node = node.parentElement;
  if (!node) throw new Error(`no select found next to label ${String(label)}`);
  return node;
}

function selectOf(label: RegExp | string): HTMLElement {
  return within(itemOf(label)).getAllByRole('combobox')[0];
}

async function choose(label: RegExp | string, option: string) {
  fireEvent.click(selectOf(label));
  fireEvent.click(await screen.findByRole('option', { name: option }));
}

function fillRequired() {
  fireEvent.change(screen.getByLabelText(/Type Name/i), { target: { value: 'Employee Handbook' } });
  fireEvent.change(screen.getByLabelText(/Allowed Extensions/i), { target: { value: 'pdf' } });
}

describe('AttachmentTypeFormDialog - Escalate to (DAS-FE-6)', () => {
  it('no longer shows the AI can read field, on create or on edit', async () => {
    renderDialog();
    expect(screen.queryByText('AI can read')).not.toBeInTheDocument();
    expect(screen.getByText('Escalate to')).toBeInTheDocument();
    cleanup();

    hooks.useAttachmentType.mockReturnValue({ data: savedType(), isLoading: false });
    renderDialog({ attachmentTypeId: 'type-1' });
    await waitFor(() => expect(selectOf('Escalate to').textContent).toMatch(/HR/));
    expect(screen.queryByText('AI can read')).not.toBeInTheDocument();
    expect(screen.queryByText(/Staff only/)).not.toBeInTheDocument();
  });

  it('shows Escalate to as an empty, clearable team select', async () => {
    renderDialog();

    fireEvent.click(selectOf('Escalate to'));
    expect(await screen.findByRole('option', { name: 'HR' })).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'Sales Support' })).toBeInTheDocument();
    expect(within(itemOf('Escalate to')).queryByRole('button', { name: /Clear selection/i })).not.toBeInTheDocument();
  });

  it('create sends no team and no ai_audience when nothing is touched', async () => {
    renderDialog();
    fillRequired();

    fireEvent.click(screen.getByRole('button', { name: /^Create$/ }));

    await waitFor(() => expect(hooks.createAsync).toHaveBeenCalledTimes(1));
    const payload = hooks.createAsync.mock.calls[0][0];
    expect(payload).toMatchObject({ ai_escalate_team_id: null });
    expect(payload).not.toHaveProperty('ai_audience');
  });

  it('create sends the chosen team id', async () => {
    renderDialog();
    fillRequired();
    await choose('Escalate to', 'HR');

    fireEvent.click(screen.getByRole('button', { name: /^Create$/ }));

    await waitFor(() => expect(hooks.createAsync).toHaveBeenCalledTimes(1));
    expect(hooks.createAsync.mock.calls[0][0]).toMatchObject({ ai_escalate_team_id: 'team-hr' });
    expect(hooks.createAsync.mock.calls[0][0]).not.toHaveProperty('ai_audience');
  });

  it('reloads the saved team by name when editing', async () => {
    hooks.useAttachmentType.mockReturnValue({ data: savedType(), isLoading: false });
    renderDialog({ attachmentTypeId: 'type-1' });

    await waitFor(() => expect(selectOf('Escalate to').textContent).toMatch(/HR/));
    expect(selectOf('Escalate to').textContent).not.toMatch(/team-hr/);
  });

  it('update keeps the saved team and sends no ai_audience when another field is edited', async () => {
    hooks.useAttachmentType.mockReturnValue({ data: savedType(), isLoading: false });
    renderDialog({ attachmentTypeId: 'type-1' });
    await waitFor(() => expect(selectOf('Escalate to').textContent).toMatch(/HR/));

    // The Update button stays disabled until the form is dirty, so edit an unrelated field.
    fireEvent.change(screen.getByLabelText(/Allowed Extensions/i), { target: { value: 'pdf,docx,doc' } });
    fireEvent.click(screen.getByRole('button', { name: /^Update$/ }));

    await waitFor(() => expect(hooks.updateAsync).toHaveBeenCalledTimes(1));
    const call = hooks.updateAsync.mock.calls[0][0];
    expect(call).toMatchObject({ id: 'type-1', data: { ai_escalate_team_id: 'team-hr' } });
    expect(call.data).not.toHaveProperty('ai_audience');
  });

  it('clearing the team sends null', async () => {
    hooks.useAttachmentType.mockReturnValue({ data: savedType(), isLoading: false });
    renderDialog({ attachmentTypeId: 'type-1' });
    await waitFor(() => expect(selectOf('Escalate to').textContent).toMatch(/HR/));

    fireEvent.pointerDown(within(itemOf('Escalate to')).getByRole('button', { name: /Clear selection/i }));
    fireEvent.click(screen.getByRole('button', { name: /^Update$/ }));

    await waitFor(() => expect(hooks.updateAsync).toHaveBeenCalledTimes(1));
    expect(hooks.updateAsync.mock.calls[0][0].data).toMatchObject({ ai_escalate_team_id: null });
  });

  it('still shows the saved team name when the team list cannot be loaded', async () => {
    hooks.getTeams.mockRejectedValue(new Error('teams unavailable'));
    hooks.useAttachmentType.mockReturnValue({ data: savedType(), isLoading: false });
    renderDialog({ attachmentTypeId: 'type-1' });

    await waitFor(() => expect(selectOf('Escalate to').textContent).toMatch(/HR/));
    expect(selectOf('Escalate to').textContent).not.toMatch(/team-hr/);
  });
});
