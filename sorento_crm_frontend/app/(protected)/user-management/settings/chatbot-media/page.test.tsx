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
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
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
    media_voice_degraded_model: null,
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

/**
 * A ModelField is a select plus a free-text box, and the page carries four of them,
 * so both halves are looked up inside the one field's own container rather than by
 * a placeholder that four fields share.
 */
function modelField(id: string) {
  const trigger = document.getElementById(id);
  if (!trigger) throw new Error(`no model field ${id}`);
  const container = trigger.closest('.space-y-2');
  if (!container) throw new Error(`model field ${id} has no container`);
  return {
    trigger,
    text: container.querySelector(
      'input[placeholder="or type a model name"]',
    ) as HTMLInputElement,
  };
}

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
    { id: 'media-burst-limit', min: 1, max: 1000, safeValid: 20 },
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

  it('rejects burstLimit = 0 (the limiter reads 0 as off, not as a lockdown)', () => {
    mockQuery.mockReturnValue({ data: settings(), isLoading: false, isError: false });
    renderWithClient();

    const input = document.getElementById('media-burst-limit') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '0' } });

    expect(screen.getByText('Enter a whole number between 1 and 1000.')).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
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

/**
 * The voice degraded model (plan section 16.1). Blank is the shipped state and it
 * means the voice quota is a hard refusal, so these pin three things: blank is not
 * an error, blank is not quietly filled from the image tier, and a value the
 * operator sets survives a save and can be taken back off again.
 */
describe('ChatbotMediaSettingsPage voice degraded model', () => {
  function mutationSpy() {
    const mutate = vi.fn();
    mockMutation.mockReturnValue({ isPending: false, mutate });
    return mutate;
  }

  it('ships blank, and blank is a valid state rather than an error', () => {
    mockQuery.mockReturnValue({ data: settings(), isLoading: false, isError: false });
    renderWithClient();

    const field = modelField('media-voice-degraded-model');
    expect(field.text).toHaveValue('');
    expect(field.trigger).toHaveTextContent('Not set');
    expect(saveButton()).toBeEnabled();
  });

  it('says what blank does, and does not raise the image field warning a second time', () => {
    mockQuery.mockReturnValue({ data: settings(), isLoading: false, isError: false });
    renderWithClient();

    expect(
      screen.getByText(
        'Set a cheaper model to keep transcribing past the monthly allowance; blank refuses instead.',
      ),
    ).toBeInTheDocument();
    // Both degraded fields are blank here. Only the image one carries the inline
    // warning; a blank voice tier is the shipped default, not a misconfiguration.
    expect(screen.getAllByText(/no degraded model set/i)).toHaveLength(1);
  });

  it('stays blank when the image tier has a model, so nothing is seeded across modalities', () => {
    mockQuery.mockReturnValue({
      data: settings({ media_image_degraded_model: 'gpt-4o-mini' }),
      isLoading: false,
      isError: false,
    });
    renderWithClient();

    expect(modelField('media-image-degraded-model').text).toHaveValue('gpt-4o-mini');
    expect(modelField('media-voice-degraded-model').text).toHaveValue('');
    expect(screen.queryByText(/no degraded model set/i)).not.toBeInTheDocument();
  });

  it('round-trips a saved value: it seeds the field and is sent back unchanged', () => {
    const mutate = mutationSpy();
    mockQuery.mockReturnValue({
      data: settings({ media_voice_degraded_model: 'gpt-4o-mini-transcribe' }),
      isLoading: false,
      isError: false,
    });
    renderWithClient();

    const field = modelField('media-voice-degraded-model');
    expect(field.text).toHaveValue('gpt-4o-mini-transcribe');
    expect(field.trigger).toHaveTextContent('GPT-4o mini transcribe');

    fireEvent.click(saveButton());

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ media_voice_degraded_model: 'gpt-4o-mini-transcribe' }),
      expect.anything(),
    );
  });

  it('sends a newly typed model, and blank as null rather than an empty string', () => {
    const mutate = mutationSpy();
    mockQuery.mockReturnValue({ data: settings(), isLoading: false, isError: false });
    renderWithClient();

    const field = modelField('media-voice-degraded-model');
    fireEvent.change(field.text, { target: { value: '  whisper-cheap  ' } });
    fireEvent.click(saveButton());
    expect(mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({ media_voice_degraded_model: 'whisper-cheap' }),
      expect.anything(),
    );

    fireEvent.change(field.text, { target: { value: '' } });
    fireEvent.click(saveButton());
    expect(mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({ media_voice_degraded_model: null }),
      expect.anything(),
    );
  });

  it('can be unset from the select itself, not only from the text box', () => {
    mockQuery.mockReturnValue({
      data: settings({ media_voice_degraded_model: 'gpt-4o-transcribe' }),
      isLoading: false,
      isError: false,
    });
    renderWithClient();

    const field = modelField('media-voice-degraded-model');
    const clear = field.trigger.querySelector('[aria-label="Clear selection"]');
    expect(clear).toBeTruthy();

    fireEvent.pointerDown(clear as Element);

    expect(modelField('media-voice-degraded-model').text).toHaveValue('');
    expect(field.trigger).toHaveTextContent('Not set');
  });
});

/**
 * Switching the image provider. A model id belongs to the provider it was picked from,
 * so both image model fields have to clear together: the standard one already did, and
 * a degraded one left behind sent the previous provider's id to the new provider, where
 * only contacts past their monthly allowance hit the unknown model. Blank is the shipped
 * state for the degraded tier, so clearing hands the operator the inline warning rather
 * than a silently wrong model.
 */
describe('ChatbotMediaSettingsPage image provider switch', () => {
  async function chooseProvider(label: string) {
    fireEvent.click(document.getElementById('media-image-provider') as HTMLElement);
    await waitFor(() =>
      expect(document.querySelectorAll('[role="option"]').length).toBeGreaterThan(0),
    );
    const option = [...document.querySelectorAll('[role="option"]')].find(
      (opt) => (opt.textContent ?? '').trim() === label,
    );
    if (!option) throw new Error(`no provider option ${label}`);
    fireEvent.click(option);
  }

  it('clears BOTH image models, and the degraded warning takes over', async () => {
    mockQuery.mockReturnValue({
      data: settings({
        media_image_provider: 'openai',
        media_image_model: 'gpt-4o',
        media_image_degraded_model: 'gpt-4o-mini',
      }),
      isLoading: false,
      isError: false,
    });
    renderWithClient();

    expect(modelField('media-image-model').text).toHaveValue('gpt-4o');
    expect(modelField('media-image-degraded-model').text).toHaveValue('gpt-4o-mini');
    expect(screen.queryByText(/no degraded model set/i)).not.toBeInTheDocument();

    await chooseProvider('Google Gemini');

    await waitFor(() =>
      expect(document.getElementById('media-image-provider')).toHaveTextContent('Google Gemini'),
    );
    expect(modelField('media-image-model').text).toHaveValue('');
    // The bug: `gpt-4o-mini` survived here, so a Gemini provider was built with an
    // OpenAI model id and only over-allowance reads failed.
    expect(modelField('media-image-degraded-model').text).toHaveValue('');
    expect(screen.getByText(/no degraded model set/i)).toBeInTheDocument();
  });

  it('leaves the voice degraded model alone, which is a different provider list', async () => {
    mockQuery.mockReturnValue({
      data: settings({
        media_image_provider: 'openai',
        media_image_degraded_model: 'gpt-4o-mini',
        media_voice_degraded_model: 'gpt-4o-mini-transcribe',
      }),
      isLoading: false,
      isError: false,
    });
    renderWithClient();

    await chooseProvider('Google Gemini');

    await waitFor(() => expect(modelField('media-image-degraded-model').text).toHaveValue(''));
    expect(modelField('media-voice-degraded-model').text).toHaveValue(
      'gpt-4o-mini-transcribe',
    );
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
