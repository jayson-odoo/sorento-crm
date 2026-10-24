/**
 * MODEL-PER-CONTACT AC-M-2: the tag form's Chatbot section has an "AI model" provider select + model
 * select writing settings.chatbot.llm = {provider, model}; clearing removes the llm key.
 * Selects are native stubs; provider select = the one holding option `gemini`, model select = the
 * one holding the mocked model.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/contact-tags/t1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
}));

const updateContactTag = vi.fn();
vi.mock('../services/contactTagService', () => ({
  updateContactTag: (...a: unknown[]) => updateContactTag(...a),
  getContactTag: vi.fn(),
  getContactTags: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0 } }),
}));

vi.mock('@/hooks/useProviderModels', () => ({
  useProviderModels: (provider: string) => ({
    data: { provider, source: 'live', message: null, models: [{ value: 'm-zzt-1', label: 'm-zzt-1' }] },
  }),
}));

vi.mock('@/components/common/SearchableSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableSelect')>();
  type Props = Parameters<typeof actual.SearchableSelect>[0];
  const Stub = ({ value, onChange, options, placeholder, disabled }: Props) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value ?? ''}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" />
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
  return { ...actual, SearchableSelect: (props: Props) => <Stub {...props} /> };
});

import ContactTagSettings from './ContactTagSettings';

const tag = (settings: Record<string, unknown>) => ({
  id: 't1', name: 'Dealer', description: null, is_active: true, sort_order: 0, settings,
  contact_count: 0, created_at: '', updated_at: '',
});

function render(settings: Record<string, unknown>, editing: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  rtlRender(
    <QueryClientProvider client={client}>
      <ContactTagSettings tag={tag(settings) as never} editing={editing} onDone={vi.fn()} />
    </QueryClientProvider>,
  );
}

const chatbot = () =>
  screen
    .getAllByTestId('settings-group')
    .find((g) => within(g).getByTestId('settings-group-title').textContent === 'Chatbot')!;

const selectHolding = (value: string) =>
  (within(chatbot()).getAllByRole('combobox') as HTMLSelectElement[]).find((s) =>
    Array.from(s.options).some((o) => o.value === value),
  );

const savedSettings = () => updateContactTag.mock.calls.at(-1)![1].settings;

beforeEach(() => {
  vi.clearAllMocks();
  updateContactTag.mockResolvedValue(tag({}));
});

describe('ContactTagSettings - AI model (AC-M-2)', () => {
  it('the Chatbot section has an AI model row with a provider select in edit mode', () => {
    render({}, true);
    expect(within(chatbot()).getByText('AI model')).toBeInTheDocument();
    expect(selectHolding('gemini')).toBeTruthy();
  });

  it('choosing a provider then a model saves settings.chatbot.llm = {provider, model}', async () => {
    render({}, true);
    fireEvent.click(within(chatbot()).getByRole('switch', { name: /set on this tag/i }));
    fireEvent.change(selectHolding('gemini')!, { target: { value: 'gemini' } });
    fireEvent.change(selectHolding('m-zzt-1')!, { target: { value: 'm-zzt-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateContactTag).toHaveBeenCalled());
    expect(savedSettings().chatbot.llm).toEqual({ provider: 'gemini', model: 'm-zzt-1' });
  });

  it('clearing the provider removes the llm key and keeps the other chatbot settings', async () => {
    render({ chatbot: { tier: 'dealer', llm: { provider: 'gemini', model: 'm-zzt-1' } } }, true);
    fireEvent.change(selectHolding('gemini')!, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateContactTag).toHaveBeenCalled());
    expect(savedSettings().chatbot).toEqual({ tier: 'dealer' });
  });

  it('view mode shows the AI model of a tag that sets one, and nothing when it sets none', () => {
    render({ chatbot: { llm: { provider: 'gemini', model: 'm-zzt-1' } } }, false);
    expect(within(chatbot()).getByText('AI model')).toBeInTheDocument();
    expect(within(chatbot()).getByText(/m-zzt-1/)).toBeInTheDocument();
  });

  it('view mode of a tag with no model has no AI model row', () => {
    render({ chatbot: { tier: 'dealer' } }, false);
    expect(within(chatbot()).queryByText('AI model')).toBeNull();
  });
});
