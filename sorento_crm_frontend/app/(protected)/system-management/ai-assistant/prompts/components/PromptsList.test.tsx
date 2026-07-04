import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PromptsList } from './PromptsList';
import type { PromptKeySummary } from '../../services/aiPromptsService';

const usePromptKeys = vi.fn();
const useHasPermission = vi.fn();

vi.mock('../../hooks/useAIAssistantPrompts', () => ({
  usePromptKeys: () => usePromptKeys(),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => useHasPermission(),
}));

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PromptsList />
    </QueryClientProvider>,
  );
}

const KEYS: PromptKeySummary[] = [
  {
    name: 'reformulator',
    role: 'Rewrite turn',
    active: true,
    activates_in: null,
    variables: ['current_date'],
    production_version: 1,
    staging_version: null,
    latest_version: 1,
    updated_at: '2026-07-03T09:00:00',
    updated_by_name: 'Seed',
  },
  {
    name: 'planner',
    role: 'Decompose task',
    active: false,
    activates_in: 'M2.5',
    variables: [],
    production_version: 1,
    staging_version: null,
    latest_version: 1,
    updated_at: '2026-07-03T09:00:00',
    updated_by_name: 'Seed',
  },
];

beforeEach(() => {
  usePromptKeys.mockReset();
  useHasPermission.mockReset();
  useHasPermission.mockReturnValue(true);
});
afterEach(() => cleanup());

describe('PromptsList', () => {
  it('shows forbidden when the user lacks permission', () => {
    useHasPermission.mockReturnValue(false);
    usePromptKeys.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    renderList();
    expect(screen.getByText(/don't have permission/i)).toBeInTheDocument();
  });

  it('renders loading state', () => {
    usePromptKeys.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderList();
    expect(screen.getByText(/Loading prompts/i)).toBeInTheDocument();
  });

  it('renders error state', () => {
    usePromptKeys.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('boom'),
    });
    renderList();
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('renders empty state', () => {
    usePromptKeys.mockReturnValue({ data: [], isLoading: false, isError: false });
    renderList();
    expect(screen.getByText(/No prompt keys registered/i)).toBeInTheDocument();
  });

  it('lists active keys and hides dormant behind the toggle', () => {
    usePromptKeys.mockReturnValue({ data: KEYS, isLoading: false, isError: false });
    renderList();
    // active key visible
    expect(screen.getByTestId('prompt-link-reformulator')).toBeInTheDocument();
    // dormant table not rendered until toggle
    expect(screen.queryByTestId('dormant-prompts-table')).not.toBeInTheDocument();
    // toggle on
    fireEvent.click(screen.getByLabelText(/Show inactive prompts/i));
    expect(screen.getByTestId('dormant-prompts-table')).toBeInTheDocument();
    expect(screen.getByTestId('prompt-link-planner')).toBeInTheDocument();
  });
});
