import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PromptDetail } from './PromptDetail';
import type { PromptVersionDetail, PromptVersionsResponse } from '../../services/aiPromptsService';

const usePromptVersions = vi.fn();
const usePromptVersion = vi.fn();
const useSaveVersion = vi.fn();
const useSetLabel = vi.fn();
const useDryRun = vi.fn();
const useHasPermission = vi.fn();

vi.mock('../../hooks/useAIAssistantPrompts', () => ({
  usePromptVersions: () => usePromptVersions(),
  usePromptVersion: () => usePromptVersion(),
  useSaveVersion: () => useSaveVersion(),
  useSetLabel: () => useSetLabel(),
  useDryRun: () => useDryRun(),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => useHasPermission(),
}));
// Container pulls SettingsProvider context we don't need in a unit test.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const META: PromptVersionsResponse = {
  name: 'router',
  role: 'Intent / routing',
  active: true,
  activates_in: null,
  variables: ['current_date'],
  labels: { production: 2, staging: null },
  versions: [
    { id: 'router-2', version: 2, commit_message: 'v2', created_by_name: 'Jay', created_at: '2026-07-03T09:00:00', labels: ['production'] },
    { id: 'router-1', version: 1, commit_message: 'seed', created_by_name: 'Seed', created_at: '2026-07-02T09:00:00', labels: [] },
  ],
};

const BASE: PromptVersionDetail = {
  id: 'router-2',
  name: 'router',
  version: 2,
  template: 'Classify {{current_date}}.',
  variables: ['current_date'],
  commit_message: 'v2',
  created_by_name: 'Jay',
  created_at: '2026-07-03T09:00:00',
  labels: ['production'],
};

const saveMutate = vi.fn();
const labelMutate = vi.fn();

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PromptDetail name="router" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [usePromptVersions, usePromptVersion, useSaveVersion, useSetLabel, useDryRun, useHasPermission].forEach((m) =>
    m.mockReset(),
  );
  saveMutate.mockReset();
  labelMutate.mockReset();
  useHasPermission.mockReturnValue(true);
  usePromptVersions.mockReturnValue({ data: META, isLoading: false, isError: false });
  usePromptVersion.mockReturnValue({ data: BASE, isLoading: false, isError: false });
  useSaveVersion.mockReturnValue({ mutate: saveMutate, isPending: false });
  useSetLabel.mockReturnValue({ mutate: labelMutate, isPending: false });
  useDryRun.mockReturnValue({ mutate: vi.fn(), isPending: false, data: undefined, isError: false });
});
afterEach(() => cleanup());

describe('PromptDetail', () => {
  it('loads the production version into the editor by default', () => {
    renderDetail();
    const editor = screen.getByTestId('prompt-editor') as HTMLTextAreaElement;
    expect(editor.value).toBe('Classify {{current_date}}.');
  });

  it('shows a green chip for a present declared var', () => {
    renderDetail();
    const chip = screen.getByTestId('var-chip-current_date');
    expect(chip.getAttribute('data-state')).toBe('present');
  });

  it('hard-blocks save when an unknown token is present', () => {
    renderDetail();
    const editor = screen.getByTestId('prompt-editor');
    fireEvent.change(editor, { target: { value: 'Classify {{current_date}} and {{bogus}}' } });
    fireEvent.change(screen.getByTestId('commit-message'), { target: { value: 'msg' } });
    expect(screen.getByTestId('var-unknown-error')).toBeInTheDocument();
    expect(screen.getByTestId('save-version')).toBeDisabled();
  });

  it('soft-warns (does not block) when a declared var is removed', () => {
    renderDetail();
    fireEvent.change(screen.getByTestId('prompt-editor'), { target: { value: 'Classify without the var.' } });
    fireEvent.change(screen.getByTestId('commit-message'), { target: { value: 'msg' } });
    expect(screen.getByTestId('var-missing-warning')).toBeInTheDocument();
    expect(screen.getByTestId('save-version')).not.toBeDisabled();
  });

  it('keeps save disabled until there is a commit message', () => {
    renderDetail();
    fireEvent.change(screen.getByTestId('prompt-editor'), { target: { value: 'Classify {{current_date}} edited.' } });
    expect(screen.getByTestId('save-version')).toBeDisabled();
    fireEvent.change(screen.getByTestId('commit-message'), { target: { value: 'msg' } });
    expect(screen.getByTestId('save-version')).not.toBeDisabled();
  });

  it('opens the publish confirm dialog for a non-production version', () => {
    renderDetail();
    fireEvent.click(screen.getByTestId('publish-production-1'));
    expect(screen.getByText('Publish router v1 to production?')).toBeInTheDocument();
    expect(screen.getByText(/changes the live assistant immediately/i)).toBeInTheDocument();
  });

  it('shows an AlertDialog (not window.confirm) when switching versions with unsaved edits', () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    renderDetail();
    // make the editor dirty
    fireEvent.change(screen.getByTestId('prompt-editor'), { target: { value: 'Classify {{current_date}} edited.' } });
    // click the other version row to switch
    fireEvent.click(screen.getByTestId('version-row-1'));
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(screen.getByText(/Discard unsaved edits\?/i)).toBeInTheDocument();
    confirmSpy.mockRestore();
  });
});
