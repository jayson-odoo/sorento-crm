/**
 * Project setup's add / edit / delete toasts name the project template a "to-do list template"
 * (owner meeting, 29 Oct), so a delete no longer shows the dialog's "To-do list template deleted"
 * next to a hook toast that still says "Template deleted".
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/toast';

const createProjectTemplate = vi.fn();
const updateProjectTemplate = vi.fn();
const deleteProjectTemplate = vi.fn();

vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    createProjectTemplate: (...args: unknown[]) => createProjectTemplate(...args),
    updateProjectTemplate: (...args: unknown[]) => updateProjectTemplate(...args),
    deleteProjectTemplate: (...args: unknown[]) => deleteProjectTemplate(...args),
  };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { useProjectTemplateMutations } from './useProjects';

function Harness({
  onReady,
}: {
  onReady: (api: ReturnType<typeof useProjectTemplateMutations>) => void;
}) {
  const api = useProjectTemplateMutations();
  React.useEffect(() => {
    onReady(api);
  }, [api, onReady]);
  return null;
}

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  let api: ReturnType<typeof useProjectTemplateMutations> | null = null;
  render(
    <QueryClientProvider client={client}>
      <Harness onReady={(value) => (api = value)} />
    </QueryClientProvider>,
  );
  return () => api!;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useProjectTemplateMutations toast wording', () => {
  it('says To-do list template created', async () => {
    createProjectTemplate.mockResolvedValue({ id: 'tp1', name: 'New build' });
    const api = mount();
    await act(async () => {
      await api().create.mutateAsync({ name: 'New build' } as never);
    });
    expect(toast.success).toHaveBeenCalledWith('To-do list template created');
  });

  it('says To-do list template saved', async () => {
    updateProjectTemplate.mockResolvedValue({ id: 'tp1', name: 'New build' });
    const api = mount();
    await act(async () => {
      await api().update.mutateAsync({ id: 'tp1', body: { name: 'New build' } });
    });
    expect(toast.success).toHaveBeenCalledWith('To-do list template saved');
  });

  it('says To-do list template deleted', async () => {
    deleteProjectTemplate.mockResolvedValue(undefined);
    const api = mount();
    await act(async () => {
      await api().remove.mutateAsync('tp1');
    });
    expect(toast.success).toHaveBeenCalledWith('To-do list template deleted');
  });
});
