/**
 * AGENTIC-P2: System > AI Assistant gets a "Jev API key" field beside the other provider keys.
 * Same contract: a saved key renders masked (`jev_api_key_masked`), an edit sends `jev_api_key`,
 * an untouched field sends undefined.
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
  jev_api_key_masked: '****7777',
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

function jevInput(): HTMLInputElement {
  const input = screen.getByText('Jev API key').parentElement?.querySelector('input');
  expect(input).toBeTruthy();
  return input as HTMLInputElement;
}

function save() {
  fireEvent.click(screen.getByRole('button', { name: /save settings/i }));
  expect(mutateConfig).toHaveBeenCalledTimes(1);
  return mutateConfig.mock.calls[0][0];
}

describe('AIAssistantSettingsForm - Jev API key field', () => {
  it('renders the saved Jev key masked', () => {
    render(<AIAssistantSettingsForm />);
    expect(jevInput()).toHaveValue('****7777');
  });

  it('sends nothing for the untouched Jev key', () => {
    render(<AIAssistantSettingsForm />);
    expect(save().jev_api_key).toBeUndefined();
  });

  it('an edit carries the new value as jev_api_key and leaves the other keys alone', () => {
    render(<AIAssistantSettingsForm />);
    fireEvent.change(jevInput(), { target: { value: 'jev-new-key' } });
    const payload = save();
    expect(payload.jev_api_key).toBe('jev-new-key');
    expect(payload.openai_api_key).toBeUndefined();
    expect(payload.gemini_api_key).toBeUndefined();
  });

  it('editing another key does not send jev_api_key', () => {
    render(<AIAssistantSettingsForm />);
    fireEvent.change(screen.getByPlaceholderText('AIza****'), { target: { value: 'g-new' } });
    expect(save().jev_api_key).toBeUndefined();
  });
});
