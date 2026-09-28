/**
 * Register a project (Pipeline > Start), owner hand test on PR #1336.
 *
 * - Progressive, the portal price tag form's pattern: the dialog opens on Who and
 *   what; Details (optional) stays collapsed until every Who and what field is filled,
 *   then opens by itself, once.
 * - The duplicate check runs on the Check button beside Project title, never on a
 *   keystroke, and once more on submit as the guard.
 * - No dialog subtitle, no helper line under Project launch date.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const listParties = vi.fn();
const listProjectTypes = vi.fn();
const listProjectTemplates = vi.fn();
const previewClashes = vi.fn();
const registerProject = vi.fn();
const push = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/pipeline',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listParties: (...args: unknown[]) => listParties(...args),
    listProjectTypes: (...args: unknown[]) => listProjectTypes(...args),
    listProjectTemplates: (...args: unknown[]) => listProjectTemplates(...args),
    previewClashes: (...args: unknown[]) => previewClashes(...args),
    registerProject: (...args: unknown[]) => registerProject(...args),
  };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="" />
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { RegisterProjectDialog } from './RegisterProjectDialog';

const BLOCKING = {
  project_id: 'p9',
  project_code: 'PRJ-000009',
  title: 'Setia Alam Phase 3B',
  outcome: 'open',
  owner_name: 'Aina',
  brands: [],
  similarity: 1,
  blocks: true,
};

function renderDialog() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RegisterProjectDialog open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
  return screen.getByRole('dialog');
}

function titleInput() {
  return screen.getByLabelText(/Project title/) as HTMLInputElement;
}

async function fillWho({ withTemplate = false } = {}) {
  await waitFor(() =>
    expect(
      within(document.getElementById('project-developer') as HTMLElement).getByText('SP Setia'),
    ).toBeInTheDocument(),
  );
  fireEvent.change(document.getElementById('project-developer') as HTMLElement, {
    target: { value: 'd1' },
  });
  await waitFor(() =>
    expect(
      within(document.getElementById('project-type') as HTMLElement).getByText('Hotel'),
    ).toBeInTheDocument(),
  );
  fireEvent.change(document.getElementById('project-type') as HTMLElement, {
    target: { value: 'ty1' },
  });
  fireEvent.change(titleInput(), { target: { value: 'Setia Alam Phase 3B' } });
  fireEvent.blur(titleInput());
  if (withTemplate) {
    await waitFor(() =>
      expect(
        within(document.getElementById('project-template') as HTMLElement).getByText(
          'Standard hotel',
        ),
      ).toBeInTheDocument(),
    );
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  listParties.mockImplementation(async (params: { party_type: string }) => ({
    data:
      params.party_type === 'developer'
        ? [{ id: 'd1', party_type: 'developer', name: 'SP Setia', is_active: true }]
        : [],
    pagination: { total: 1, page: 1, limit: 200 },
  }));
  listProjectTypes.mockResolvedValue([
    {
      id: 'ty1',
      name: 'Hotel',
      code: 'HOTEL',
      derives_delivery_from_launch: true,
      sort_order: 1,
      is_active: true,
    },
  ]);
  listProjectTemplates.mockResolvedValue([]);
  previewClashes.mockResolvedValue({ candidates: [], would_block: false });
  registerProject.mockResolvedValue({ id: 'new1', project_code: 'PRJ-000010' });
});

describe('RegisterProjectDialog: no subtitle, no helper text', () => {
  it('has a title and no subtitle under it', () => {
    const dialog = renderDialog();
    expect(within(dialog).getByText('Register a project')).toBeInTheDocument();
    expect(within(dialog).queryByText('Claim the development first.')).toBeNull();
    expect(dialog.querySelector('[data-slot="dialog-description"]')).toBeNull();
  });

  it('has no helper line under Project launch date', async () => {
    const dialog = renderDialog();
    await fillWho();
    await waitFor(() => expect(screen.getByLabelText('Project launch date')).toBeInTheDocument());
    expect(within(dialog).queryByText(/Expected delivery is derived/)).toBeNull();
  });
});

describe('RegisterProjectDialog: progressive, the portal price tag pattern', () => {
  it('opens on Who and what with Details (optional) collapsed', () => {
    renderDialog();
    expect(screen.getByRole('button', { name: /Who and what/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByRole('button', { name: /Details \(optional\)/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.queryByLabelText('Location')).toBeNull();
  });

  it('keeps Details collapsed while a Who and what field is still empty', async () => {
    renderDialog();
    fireEvent.change(titleInput(), { target: { value: 'Setia Alam Phase 3B' } });
    fireEvent.blur(titleInput());
    await waitFor(() => expect(listProjectTypes).toHaveBeenCalled());
    expect(screen.queryByLabelText('Location')).toBeNull();
  });

  it('expands Details once every Who and what field is filled', async () => {
    renderDialog();
    await fillWho();
    await waitFor(() => expect(screen.getByLabelText('Location')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /Details \(optional\)/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('does not open Details on the first letter of the title (the title counts once left)', async () => {
    renderDialog();
    await waitFor(() => expect(listProjectTypes).toHaveBeenCalled());
    await waitFor(() =>
      expect(
        within(document.getElementById('project-type') as HTMLElement).getByText('Hotel'),
      ).toBeInTheDocument(),
    );
    fireEvent.change(document.getElementById('project-developer') as HTMLElement, {
      target: { value: 'd1' },
    });
    fireEvent.change(document.getElementById('project-type') as HTMLElement, {
      target: { value: 'ty1' },
    });
    fireEvent.change(titleInput(), { target: { value: 'S' } });
    expect(screen.queryByLabelText('Location')).toBeNull();
    fireEvent.blur(titleInput());
    await waitFor(() => expect(screen.getByLabelText('Location')).toBeInTheDocument());
  });

  it('waits for the Template when the chosen type offers one', async () => {
    listProjectTemplates.mockResolvedValue([
      { id: 'tp1', name: 'Standard hotel', has_forked_status_graph: false },
    ]);
    renderDialog();
    await fillWho({ withTemplate: true });
    expect(screen.queryByLabelText('Location')).toBeNull();
    fireEvent.change(document.getElementById('project-template') as HTMLElement, {
      target: { value: 'tp1' },
    });
    await waitFor(() => expect(screen.getByLabelText('Location')).toBeInTheDocument());
  });

  it('never reopens Details the user folded by hand', async () => {
    renderDialog();
    await fillWho();
    await waitFor(() => expect(screen.getByLabelText('Location')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Details \(optional\)/ }));
    expect(screen.queryByLabelText('Location')).toBeNull();
    fireEvent.change(titleInput(), { target: { value: 'Setia Alam Phase 3C' } });
    fireEvent.blur(titleInput());
    expect(screen.queryByLabelText('Location')).toBeNull();
  });

  it('lets the user open Details by hand before Who and what is done', () => {
    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: /Details \(optional\)/ }));
    expect(screen.getByLabelText('Location')).toBeInTheDocument();
  });
});

describe('RegisterProjectDialog: Check button, not a check per keystroke', () => {
  it('typing the title runs no duplicate check', async () => {
    renderDialog();
    for (const value of ['Seti', 'Setia', 'Setia Alam', 'Setia Alam Phase 3B']) {
      fireEvent.change(titleInput(), { target: { value } });
    }
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(previewClashes).not.toHaveBeenCalled();
  });

  it('Check sits beside the title and is off until the title is long enough', () => {
    renderDialog();
    const check = screen.getByRole('button', { name: 'Check' });
    expect(titleInput().parentElement).toContainElement(check);
    expect(check).toBeDisabled();
    fireEvent.change(titleInput(), { target: { value: 'Seti' } });
    expect(check).toBeEnabled();
  });

  it('Check runs the check once and says inline when nothing matches', async () => {
    renderDialog();
    fireEvent.change(titleInput(), { target: { value: 'Setia Alam Phase 3B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    await waitFor(() =>
      expect(screen.getByText('No existing project matches this title.')).toBeInTheDocument(),
    );
    expect(previewClashes).toHaveBeenCalledTimes(1);
    expect(previewClashes).toHaveBeenCalledWith({
      title: 'Setia Alam Phase 3B',
      developer_party_id: null,
    });
  });

  it('Check shows a blocking match inline and blocks Register', async () => {
    previewClashes.mockResolvedValue({ candidates: [BLOCKING], would_block: true });
    renderDialog();
    fireEvent.change(titleInput(), { target: { value: 'Setia Alam Phase 3B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    await waitFor(() =>
      expect(screen.getByText('Already registered to someone else')).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: 'Blocked by an existing project' })).toBeDisabled();
  });

  it('editing the title clears the result it was not asked about', async () => {
    previewClashes.mockResolvedValue({ candidates: [BLOCKING], would_block: true });
    renderDialog();
    fireEvent.change(titleInput(), { target: { value: 'Setia Alam Phase 3B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    await waitFor(() =>
      expect(screen.getByText('Already registered to someone else')).toBeInTheDocument(),
    );
    fireEvent.change(titleInput(), { target: { value: 'Setia Alam Phase 4' } });
    expect(screen.queryByText('Already registered to someone else')).toBeNull();
    expect(screen.getByRole('button', { name: 'Register project' })).toBeEnabled();
  });
});

describe('RegisterProjectDialog: one duplicate check on submit, the guard', () => {
  it('submit runs the check once and registers when clear', async () => {
    renderDialog();
    fireEvent.change(titleInput(), { target: { value: 'Setia Alam Phase 3B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(1));
    expect(previewClashes).toHaveBeenCalledTimes(1);
    expect(push).toHaveBeenCalledWith('/project-sales/new1');
  });

  it('submit stops on a blocking match even when Check was never pressed', async () => {
    previewClashes.mockResolvedValue({ candidates: [BLOCKING], would_block: true });
    renderDialog();
    fireEvent.change(titleInput(), { target: { value: 'Setia Alam Phase 3B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() =>
      expect(screen.getByText('Already registered to someone else')).toBeInTheDocument(),
    );
    expect(previewClashes).toHaveBeenCalledTimes(1);
    expect(registerProject).not.toHaveBeenCalled();
  });
});
