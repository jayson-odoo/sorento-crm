/**
 * AGENTIC-P2-ROUTE review fix: a stored Jev key can be cleared. The button appears only when a
 * key is stored; clicking it sends `typesafe_api_key_clear: true` on save and no typesafe_api_key.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import AIAssistantSettingsForm from './AIAssistantSettingsForm';

const BASE = {
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
let config: Record<string, unknown> = { ...BASE, typesafe_api_key_masked: '****7777' };
const mutateConfig = vi.fn();

vi.mock('../hooks/useAIAssistantAdmin', () => ({
  useAIAssistantConfig: () => ({ data: config, isLoading: false, isError: false, error: null }),
  useAIAssistantTools: () => ({ data: [], isLoading: false, isError: false, error: null }),
  useUpdateAIAssistantConfig: () => ({ mutate: mutateConfig, isPending: false }),
  useTestAIAssistantConnection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/useProviderModels', () => ({
  useProviderModels: () => ({ data: { provider: 'gemini', source: 'live', message: null, models: [] } }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => {
  mutateConfig.mockClear();
  config = { ...BASE, typesafe_api_key_masked: '****7777' };
});
afterEach(() => cleanup());

const clearButton = () => screen.queryByRole('button', { name: 'Clear TypeSafe (Jev) API key' });
const save = () => {
  fireEvent.click(screen.getByRole('button', { name: /save settings/i }));
  expect(mutateConfig).toHaveBeenCalledTimes(1);
  return mutateConfig.mock.calls[0][0];
};

describe('AIAssistantSettingsForm - clearing the Jev key', () => {
  it('shows the clear button when a key is stored', () => {
    render(<AIAssistantSettingsForm />);
    expect(clearButton()).toBeInTheDocument();
  });

  it('shows no clear button when no key is stored', () => {
    config = { ...BASE, typesafe_api_key_masked: '' };
    render(<AIAssistantSettingsForm />);
    expect(clearButton()).not.toBeInTheDocument();
  });

  it('shows no clear button when the masked value is missing', () => {
    config = { ...BASE };
    render(<AIAssistantSettingsForm />);
    expect(clearButton()).not.toBeInTheDocument();
  });

  it('clicking it sends typesafe_api_key_clear true and no typesafe_api_key on save', () => {
    render(<AIAssistantSettingsForm />);
    fireEvent.click(clearButton() as HTMLElement);
    const payload = save();
    expect(payload.typesafe_api_key_clear).toBe(true);
    expect(payload.typesafe_api_key).toBeUndefined();
  });

  it('without a click the clear flag is not sent as true', () => {
    render(<AIAssistantSettingsForm />);
    expect(save().typesafe_api_key_clear).not.toBe(true);
  });
});
