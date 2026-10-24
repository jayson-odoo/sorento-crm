/**
 * MODEL-PER-CONTACT AC-M-15: the contact Chatbot section shows an "AI model" row (provider select +
 * model select, clearable) and one source line. Selects are stubbed as native <select> (the
 * pattern of ContactChatbotSection.test.tsx); the provider select is found by holding the option
 * `gemini`, the model select by holding the mocked model. Assumed: the profile read carries
 * `chatbot_llm`, the save input carries `llm` ({provider, model} | null).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactChatbotSection from './ContactChatbotSection';

const useContactChatbotProfile = vi.fn();
const mutate = vi.fn();

vi.mock('../hooks/useContactChatbot', () => ({
  useContactChatbotProfile: (...a: unknown[]) => useContactChatbotProfile(...a),
  useSaveContactChatbotProfile: () => ({ mutate, isPending: false }),
  useSaveContactEscalation: () => ({ mutate: vi.fn(), isPending: false }),
  useSaveContactChatbotAllowed: () => ({ mutate: vi.fn(), isPending: false }),
  useContactChatbotMemory: () => ({
    data: {
      level: { own: null, effective: 'off', system_default: 'off' },
      facts: [],
      vocabulary: [],
      episodes: { kept: 0, limit: 20, current: null, rows: [] },
      open_orders: { customer_name: null, rows: [] },
    },
    isLoading: false,
    isError: false,
  }),
  useSaveContactFact: () => ({ mutate: vi.fn(), isPending: false }),
  contactChatbotMemoryQueryKey: (id: string) => ['contact-chatbot-memory', id],
}));

const granted = new Set<string>(['system.ai_assistant_settings.edit']);
vi.mock('@/hooks/usePermissions', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/usePermissions')>();
  return { ...actual, useHasPermission: (slug: string) => granted.has(slug) };
});

vi.mock('@/hooks/useProviderModels', () => ({
  useProviderModels: (provider: string) => ({
    data: { provider, source: 'live', message: null, models: [{ value: 'm-zzt-1', label: 'm-zzt-1' }] },
  }),
}));

vi.mock('@/components/common/SearchableSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableSelect')>();
  type Props = Parameters<typeof actual.SearchableSelect>[0];
  const Stub = ({ value, onChange, options, placeholder, disabled, clearable }: Props) => (
    <select
      aria-label={placeholder ?? 'select'}
      data-clearable={clearable === undefined ? 'unset' : String(clearable)}
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

const BASE = {
  chatbot_memory_level: null,
  tier: null,
  default_ledgers: [],
  stock_allowed: true,
  notify_salesman: false,
  packing_list_allowed: false,
  eta_offset_applied: true,
  escalation_allowed: true,
  chatbot_allowed: true,
  skip_period_questions: false,
  files_as_links: false,
};
const NONE = { provider: null, model: null, source: 'none', tags: [] };

function show(chatbot_llm: unknown) {
  useContactChatbotProfile.mockReturnValue({ data: { ...BASE, chatbot_llm }, isLoading: false, isError: false });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactChatbotSection contactId="c1" />
    </QueryClientProvider>,
  );
}

const selectHolding = (value: string) =>
  (screen.getAllByRole('combobox') as HTMLSelectElement[]).find((s) =>
    Array.from(s.options).some((o) => o.value === value),
  );

beforeEach(() => {
  granted.clear();
  granted.add('system.ai_assistant_settings.edit');
  useContactChatbotProfile.mockReset();
  mutate.mockReset();
});
afterEach(() => cleanup());

describe('ContactChatbotSection - AI model (AC-M-15)', () => {
  it('shows the AI model row with a provider select and, once a provider is set, a clearable model select', () => {
    show({ provider: 'gemini', model: 'm-zzt-1', source: 'contact', tags: [] });
    expect(screen.getByText('AI model')).toBeInTheDocument();
    expect(selectHolding('gemini')).toBeTruthy();
    expect(selectHolding('gemini')).toHaveAttribute('data-clearable', 'true');
    expect(selectHolding('m-zzt-1')).toBeTruthy();
    expect(selectHolding('m-zzt-1')).toHaveAttribute('data-clearable', 'true');
  });

  it.each([
    [{ provider: 'gemini', model: 'g', source: 'tag', tags: ['Office Staff'] }, 'From tag Office Staff: Google Gemini g'],
    [{ provider: 'gemini', model: 'g', source: 'tag', tags: ['Office Staff', 'Sorento Dealer'] }, 'From tag Office Staff, Sorento Dealer: Google Gemini g'],
    [{ provider: null, model: null, source: 'tag_conflict', tags: ['Office Staff', 'Sorento Dealer'] }, 'Tags disagree: Office Staff, Sorento Dealer'],
    [{ provider: 'openai', model: 'gpt-4.1', source: 'contact', tags: [] }, 'Set on this contact'],
    [NONE, 'Default'],
  ])('source line for %j reads exactly %s', (llm, line) => {
    show(llm);
    expect(screen.getByText(line)).toBeInTheDocument();
  });

  it('names the model the tag runs on: provider label plus model', () => {
    show({ provider: 'gemini', model: 'gemini-3.5-flash-lite', source: 'tag', tags: ['Office Staff'] });
    expect(screen.getByText('From tag Office Staff: Google Gemini gemini-3.5-flash-lite')).toBeInTheDocument();
  });

  it.each([
    [{ provider: 'gemini', model: 'gemini-3.5-flash-lite', source: 'tag', tags: ['Office Staff'] }],
    [{ provider: null, model: null, source: 'tag_conflict', tags: ['Office Staff', 'Sorento Dealer'] }],
    [NONE],
  ])('F1: source %j leaves the override provider select empty, labelled "No override"', (llm) => {
    show(llm);
    const provider = screen.getByLabelText('No override') as HTMLSelectElement;
    expect(provider.value).toBe('');
    expect(screen.queryByDisplayValue('m-zzt-1')).toBeNull();
    // no model select appears for a tag-decided or default choice
    expect(selectHolding('m-zzt-1')).toBeUndefined();
  });

  it('F1: only source "contact" pre-fills the override provider select', () => {
    show({ provider: 'gemini', model: 'm-zzt-1', source: 'contact', tags: [] });
    expect((selectHolding('gemini') as HTMLSelectElement).value).toBe('gemini');
  });

  it('AC-S-4: without system.ai_assistant_settings.edit the picker is read-only and the source line stays', () => {
    granted.clear();
    show({ provider: 'gemini', model: 'm-zzt-1', source: 'contact', tags: [] });
    expect(selectHolding('gemini')).toBeDisabled();
    expect(selectHolding('m-zzt-1')).toBeDisabled();
    expect(screen.getByText('Set on this contact')).toBeInTheDocument();
  });

  it('AC-S-4: without the permission a tag-decided contact still shows its source line, picker disabled', () => {
    granted.clear();
    show({ provider: 'gemini', model: 'gemini-3.5-flash-lite', source: 'tag', tags: ['Office Staff'] });
    expect(screen.getByLabelText('No override')).toBeDisabled();
    expect(screen.getByText('From tag Office Staff: Google Gemini gemini-3.5-flash-lite')).toBeInTheDocument();
  });

  it('AC-S-4: with the permission the picker is editable', () => {
    show(NONE);
    expect(screen.getByLabelText('No override')).not.toBeDisabled();
  });

  it('shows the source line "Default" when the profile has no chatbot_llm at all', () => {
    show(undefined);
    expect(screen.getByText('Default')).toBeInTheDocument();
  });

  it('shows a UUID nowhere in the AI model row', () => {
    const { container } = show({ provider: 'gemini', model: 'g', source: 'tag', tags: ['Office Staff'] });
    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
  });

  it('choosing a provider then a model saves {provider, model} and never a half pair', () => {
    show(NONE);
    fireEvent.change(selectHolding('openai')!, { target: { value: 'openai' } });
    fireEvent.change(selectHolding('m-zzt-1')!, { target: { value: 'm-zzt-1' } });
    const llms = mutate.mock.calls.map((c) => c[0].llm).filter((l) => l !== undefined);
    expect(llms.at(-1)).toEqual({ provider: 'openai', model: 'm-zzt-1' });
    for (const l of llms) expect(l === null || (l.provider && l.model)).toBeTruthy();
  });

  it('clearing the override saves llm: null', () => {
    show({ provider: 'gemini', model: 'm-zzt-1', source: 'contact', tags: [] });
    fireEvent.change(selectHolding('gemini')!, { target: { value: '' } });
    expect(mutate).toHaveBeenCalled();
    expect(mutate.mock.calls.at(-1)![0]).toHaveProperty('llm', null);
  });

  it('an unrelated save does not carry llm', () => {
    show({ provider: 'gemini', model: 'm-zzt-1', source: 'contact', tags: [] });
    fireEvent.click(screen.getByLabelText(/stock checks/i));
    expect(mutate.mock.calls[0][0].llm).toBeUndefined();
  });
});
