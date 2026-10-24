/**
 * MODEL-PER-CONTACT R4 / AC-R4-9: System > AI Assistant gets an "OpenAI API key" field beside the
 * Anthropic and Gemini ones. Same contract as the other key fields: a saved key renders masked
 * (`openai_api_key_masked`), an edit sends `openai_api_key`, an untouched field sends undefined.
 * Assumed: the field is the input in the same wrapper as the label text "OpenAI API key".
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import AIAssistantSettingsForm from './AIAssistantSettingsForm';

const CONFIG = {
  id: 'cfg-1',
  provider: 'gemini',
  model: 'gemini-2.5-flash',
  temperature: 0,
  system_prompt: '',
  api_key_masked: '****1234',
  openai_api_key_masked: '****5555',
  anthropic_api_key_masked: '****2222',
  gemini_api_key_masked: '****3333',
  enabled_tools: [],
  rag_enabled: true,
  is_enabled: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mutateConfig = vi.fn();

vi.mock('../hooks/useAIAssistantAdmin', () => ({
  useAIAssistantConfig: () => ({ data: CONFIG, isLoading: false, isError: false, error: null }),
  useAIAssistantTools: () => ({ data: [], isLoading: false, isError: false, error: null }),
  useUpdateAIAssistantConfig: () => ({ mutate: mutateConfig, isPending: false }),
  useTestAIAssistantConnection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/useProviderModels', () => ({
  useProviderModels: () => ({ data: { provider: 'gemini', source: 'live', message: null, models: [] } }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => mutateConfig.mockClear());
afterEach(() => cleanup());

function openaiInput(): HTMLInputElement {
  const label = screen.getByText('OpenAI API key');
  const input = label.parentElement?.querySelector('input');
  expect(input).toBeTruthy();
  return input as HTMLInputElement;
}

function save() {
  fireEvent.click(screen.getByRole('button', { name: /save settings/i }));
  expect(mutateConfig).toHaveBeenCalledTimes(1);
  return mutateConfig.mock.calls[0][0];
}

describe('AIAssistantSettingsForm - OpenAI API key field (AC-R4-9)', () => {
  it('renders the saved OpenAI key masked', () => {
    render(<AIAssistantSettingsForm />);
    expect(openaiInput()).toHaveValue('****5555');
  });

  it('sends nothing for the untouched OpenAI key', () => {
    render(<AIAssistantSettingsForm />);
    expect(save().openai_api_key).toBeUndefined();
  });

  it('an edit carries the new value as openai_api_key and leaves the other keys alone', () => {
    render(<AIAssistantSettingsForm />);
    fireEvent.change(openaiInput(), { target: { value: 'sk-new-openai-key' } });
    const payload = save();
    expect(payload.openai_api_key).toBe('sk-new-openai-key');
    expect(payload.api_key).toBeUndefined();
    expect(payload.gemini_api_key).toBeUndefined();
    expect(payload.anthropic_api_key).toBeUndefined();
  });

  it('editing another key does not send openai_api_key', () => {
    render(<AIAssistantSettingsForm />);
    fireEvent.change(screen.getByPlaceholderText('AIza****'), { target: { value: 'g-new' } });
    const payload = save();
    expect(payload.gemini_api_key).toBe('g-new');
    expect(payload.openai_api_key).toBeUndefined();
  });
});
