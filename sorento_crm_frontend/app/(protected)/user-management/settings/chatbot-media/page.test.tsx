/**
 * Settings -> Chatbot Media (UAC S1-04).
 *
 * Mocks the hooks module directly so each test can drive query/mutation state
 * precisely: error, loading, success, and a mutation whose onSuccess re-syncs the
 * form from a server-returned value that differs from what was typed.
 *
 * The error-state-before-loading-state test (`renders the error state`) is the
 * exact regression recorded in the plan section 16.3: `isLoading || !draft` was
 * checked before `isError`, so a failed load showed skeletons forever and the
 * error Alert was unreachable. This test must fail against that ordering.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

Element.prototype.scrollIntoView = vi.fn();
(Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const mockQuery = vi.fn();
const mockMutation = vi.fn();

vi.mock('./hooks/useChatbotMediaSettings', () => ({
  useChatbotMediaSettings: () => mockQuery(),
  useSaveChatbotMediaSettings: () => mockMutation(),
}));

import ChatbotMediaSettingsPage from './page';
import type { ChatbotMediaSettings } from './services/chatbotMediaSettingsService';

function settings(overrides: Partial<ChatbotMediaSettings> = {}): ChatbotMediaSettings {
  return {
    media_image_monthly_limit: 50,
    media_voice_monthly_limit: 100,
    media_voice_max_seconds: 120,
    media_burst_limit: 5,
    media_burst_window_seconds: 60,
    media_warn_threshold_percent: 80,
    media_image_provider: null,
    media_image_model: null,
    media_image_degraded_model: null,
    media_transcribe_model: 'whisper-1',
    media_language_mode: 'pinned',
    media_language_pinned: 'en',
    media_language_hints: 'en,ms,zh',
    media_sync_wait_seconds: 30,
    media_extraction_timeout_seconds: 45,
    media_max_entities: 10,
    ...overrides,
  };
}

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatbotMediaSettingsPage />
    </QueryClientProvider>,
  );
}

function skeletonCount() {
  return document.querySelectorAll('[data-slot="skeleton"]').length;
}

const saveButton = () => screen.getByRole('button', { name: /save settings/i });

beforeEach(() => {
  mockQuery.mockReset();
  mockMutation.mockReset();
  mockMutation.mockReturnValue({ isPending: false, mutate: vi.fn() });
});

afterEach(() => cleanup());

describe('ChatbotMediaSettingsPage query states', () => {
  it('renders the error Alert, not loading skeletons, when the settings query fails', () => {
    mockQuery.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderWithClient();

    expect(
      screen.getByText(/chatbot media settings could not be loaded/i),
    ).toBeInTheDocument();
    expect(skeletonCount()).toBe(0);
  });

  it('renders skeletons while loading, not the error Alert', () => {
    mockQuery.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderWithClient();

    expect(skeletonCount()).toBeGreaterThan(0);
    expect(
      screen.queryByText(/chatbot media settings could not be loaded/i),
    ).not.toBeInTheDocument();
  });

  it('seeds the form from the fetched values on success', () => {
    mockQuery.mockReturnValue({
      data: settings({ media_image_monthly_limit: 77, media_burst_limit: 3 }),
      isLoading: false,
      isError: false,
    });
    renderWithClient();

    expect(screen.getByLabelText(/photos per contact per month/i)).toHaveValue('77');
    expect(screen.getByLabelText(/items per burst window/i)).toHaveValue('3');
    expect(skeletonCount()).toBe(0);
  });
});

describe('ChatbotMediaSettingsPage numeric bounds', () => {
  const FIELDS: Array<{ id: string; min: number; max: number; safeValid: number }> = [
    { id: 'media-image-monthly-limit', min: 0, max: 100000, safeValid: 500 },
    { id: 'media-voice-monthly-limit', min: 0, max: 100000, safeValid: 500 },
    { id: 'media-voice-max-seconds', min: 1, max: 3600, safeValid: 200 },
    { id: 'media-burst-limit', min: 0, max: 1000, safeValid: 20 },
    { id: 'media-burst-window', min: 1, max: 3600, safeValid: 90 },
    { id: 'media-warn-threshold', min: 1, max: 100, safeValid: 70 },
    // Chosen so it never trips the sync-wait/extraction-timeout cross-field rule
    // against the OTHER field's default value used in these per-field tests.
    { id: 'media-sync-wait', min: 5, max: 90, safeValid: 5 },
    { id: 'media-extraction-timeout', min: 5, max: 110, safeValid: 60 },
    { id: 'media-max-entities', min: 1, max: 100, safeValid: 25 },
  ];

  it.each(FIELDS)(
    'bounds $id to [$min, $max]: out-of-range and non-numeric are refused, a valid value clears the error',
    ({ id, min, max, safeValid }) => {
      mockQuery.mockReturnValue({ data: settings(), isLoading: false, isError: false });
      renderWithClient();

      const message = `Enter a whole number between ${min} and ${max}.`;
      const input = document.getElementById(id) as HTMLInputElement;
      expect(input).toBeTruthy();

      fireEvent.change(input, { target: { value: String(max + 1) } });
      expect(screen.getByText(message)).toBeInTheDocument();
      expect(saveButton()).toBeDisabled();

      fireEvent.change(input, { target: { value: 'abc' } });
      expect(screen.getByText(message)).toBeInTheDocument();
      expect(saveButton()).toBeDisabled();

      fireEvent.change(input, { target: { value: String(safeValid) } });
      expect(screen.queryByText(message)).not.toBeInTheDocument();
      expect(saveButton()).toBeEnabled();
    },
  );

  it('accepts burstLimit = 0 (0 turns pacing off)', () => {
    mockQuery.mockReturnValue({ data: settings(), isLoading: false, isError: false });
    renderWithClient();

    const input = document.getElementById('media-burst-limit') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '0' } });

    expect(screen.queryByText('Enter a whole number between 0 and 1000.')).not.toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
  });

  it('rejects voiceMaxSeconds = 0 (a clip must be at least 1 second)', () => {
    mockQuery.mockReturnValue({ data: settings(), isLoading: false, isError: false });
    renderWithClient();

    const input = document.getElementById('media-voice-max-seconds') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '0' } });

    expect(screen.getByText('Enter a whole number between 1 and 3600.')).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });
});

describe('ChatbotMediaSettingsPage cross-field rule', () => {
  it('flags an extraction timeout below the synchronous wait, on the timeout field only', () => {
    mockQuery.mockReturnValue({
      data: settings({ media_sync_wait_seconds: 30 }),
      isLoading: false,
      isError: false,
    });
    renderWithClient();

    const timeoutInput = document.getElementById('media-extraction-timeout') as HTMLInputElement;
    fireEvent.change(timeoutInput, { target: { value: '20' } });

    expect(
      screen.getByText(
        'Must be at least the synchronous wait of 30 seconds, or a job that outlives the wait is killed instead of finishing.',
      ),
    ).toBeInTheDocument();
    expect(document.getElementById('media-extraction-timeout-error')).toBeInTheDocument();
    // The sync-wait field itself carries no error - the message names the timeout.
    expect(document.getElementById('media-sync-wait-error')).not.toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });
});

describe('ChatbotMediaSettingsPage save re-sync', () => {
  it('re-seeds the form from the values the mutation actually returns', () => {
    const mutate = vi.fn(
      (
        _input: ChatbotMediaSettings,
        opts?: { onSuccess?: (saved: ChatbotMediaSettings) => void },
      ) => {
        opts?.onSuccess?.(settings({ media_image_monthly_limit: 999 }));
      },
    );
    mockQuery.mockReturnValue({
      data: settings({ media_image_monthly_limit: 50 }),
      isLoading: false,
      isError: false,
    });
    mockMutation.mockReturnValue({ isPending: false, mutate });
    renderWithClient();

    const input = document.getElementById('media-image-monthly-limit') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '123' } });
    expect(input).toHaveValue('123');

    fireEvent.click(saveButton());

    expect(mutate).toHaveBeenCalled();
    expect(input).toHaveValue('999');
  });
});
