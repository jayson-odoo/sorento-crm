/**
 * UI v2 phase 0, slice S4 (red first). UAC C-8.
 *
 * EXPORT CONTRACT (the module does not exist yet; the coder implements exactly this):
 *   app/(protected)/user-management/settings/appearance/page.tsx : default export AppearancePage()
 *     Reads the saved company theme from `useSettings()` ('../components/settings-context'):
 *       settings.theme?: { preset: PresetId; customHex: string | null }   (camelCase; the manual
 *       `mapSettingsFromApi` in settings/layout.tsx maps the API's `theme.custom_hex`). Missing means
 *       Sorento Blue, no custom colour.
 *     Uses `PRESETS` ('@/lib/theme/presets'), `generateTheme(hex, mode)` ('@/lib/theme/generate') and
 *       `contrastRatio(fg, bg)` ('@/lib/theme/contrast') - mocked here.
 *     UI (accessible names are the contract):
 *       - role="radiogroup" aria-label "Brand colour" with one role="radio" per preset, named by the preset
 *         label; aria-checked="true" on the draft's preset, none when a custom colour is typed;
 *       - a textbox "Custom colour" (hex text, e.g. #7c3aed), empty unless a custom colour is saved;
 *       - a live readout "Button text {ratio to 1 dp}:1, passes" where ratio = contrastRatio(
 *         tokens['primary-foreground'], tokens.primary) of generateTheme(draftHex, 'light');
 *       - two preview groups role="group" aria-label "Light preview" and "Dark preview", each with a button
 *         "Preview button", a badge "Preview badge" and a selected row "Preview row"; they use
 *         generateTheme(draftHex, 'light') and generateTheme(draftHex, 'dark');
 *       - button "Save": PUT apiFetch('/api/user-management/settings/general', { method: 'PUT', body }) with
 *         body JSON { theme: { preset, custom_hex } } and nothing else; custom_hex is null unless a valid custom
 *         colour is typed, and then preset is any of the five preset ids. Disabled while the typed custom
 *         colour is not a valid #rrggbb. On success invalidates the react-query cache (invalidateQueries);
 *       - button "Reset to Sorento Blue": sets the DRAFT to preset sorento-blue and clears the custom colour;
 *         it does not save by itself.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type MockTheme = { preset: string; customHex: string | null } | undefined;
const mockSettings: { theme: MockTheme } = { theme: { preset: 'sorento-blue', customHex: null } };
vi.mock('../components/settings-context', () => ({
  useSettings: () => ({ settings: mockSettings, roles: [] }),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('@/lib/toast', () => ({ toast: Object.assign(vi.fn(), { custom: vi.fn(), error: vi.fn(), success: vi.fn() }) }));

vi.mock('@/lib/theme/presets', () => ({
  PRESETS: [
    { id: 'sorento-blue', label: 'Sorento Blue', hex: '#3b82f6' },
    { id: 'sorento-red', label: 'Sorento Red', hex: '#b44d2e' },
    { id: 'teal', label: 'Teal', hex: '#0f766e' },
    { id: 'graphite', label: 'Graphite', hex: '#3f3f46' },
    { id: 'indigo', label: 'Indigo', hex: '#4f46e5' },
  ],
}));
const generateTheme = vi.fn((hex: string, mode: 'light' | 'dark') => ({
  ramp: {},
  tokens: {
    primary: mode === 'light' ? '#246bdd' : '#60a5fa',
    'primary-hover': '#1f5cc0',
    'primary-foreground': mode === 'light' ? '#ffffff' : '#0a1a3a',
    'primary-soft': '#e6efff',
    ring: '#246bdd',
  },
  background: mode === 'light' ? '#ffffff' : '#111113',
  _hex: hex,
}));
vi.mock('@/lib/theme/generate', () => ({ generateTheme: (h: string, m: 'light' | 'dark') => generateTheme(h, m) }));
vi.mock('@/lib/theme/contrast', () => ({ contrastRatio: () => 5.04 }));

import AppearancePage from './page';

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(qc, 'invalidateQueries');
  render(
    <QueryClientProvider client={qc}>
      <AppearancePage />
    </QueryClientProvider>,
  );
  return { invalidate };
}

const radio = (name: string) => screen.getByRole('radio', { name });
const sentBody = () => JSON.parse(apiFetch.mock.calls[0][1].body);

beforeEach(() => {
  apiFetch.mockReset();
  generateTheme.mockClear();
  mockSettings.theme = { preset: 'sorento-blue', customHex: null };
});
afterEach(cleanup);

describe('Settings > Appearance (C-8)', () => {
  it('shows the five presets as radios with the saved one checked', () => {
    mockSettings.theme = { preset: 'teal', customHex: null };
    mount();
    expect(screen.getByRole('radiogroup', { name: 'Brand colour' })).toBeInTheDocument();
    expect(screen.getAllByRole('radio').map((r) => r.getAttribute('aria-label') ?? r.textContent?.trim())).toEqual([
      'Sorento Blue',
      'Sorento Red',
      'Teal',
      'Graphite',
      'Indigo',
    ]);
    expect(radio('Teal')).toHaveAttribute('aria-checked', 'true');
    expect(radio('Sorento Blue')).toHaveAttribute('aria-checked', 'false');
  });

  it('with no saved theme it falls back to Sorento Blue', () => {
    mockSettings.theme = undefined;
    mount();
    expect(radio('Sorento Blue')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('textbox', { name: 'Custom colour' })).toHaveValue('');
  });

  it('clicking a swatch selects it', () => {
    mount();
    fireEvent.click(radio('Indigo'));
    expect(radio('Indigo')).toHaveAttribute('aria-checked', 'true');
    expect(radio('Sorento Blue')).toHaveAttribute('aria-checked', 'false');
  });

  it('shows the measured contrast of the button text for the draft colour', () => {
    mount();
    expect(screen.getByText('Button text 5.0:1, passes')).toBeInTheDocument();
    expect(generateTheme).toHaveBeenCalledWith('#3b82f6', 'light');
  });

  it('a typed custom colour deselects the presets and drives the generator', async () => {
    mount();
    fireEvent.change(screen.getByRole('textbox', { name: 'Custom colour' }), { target: { value: '#7c3aed' } });
    for (const r of screen.getAllByRole('radio')) expect(r).toHaveAttribute('aria-checked', 'false');
    await waitFor(() => expect(generateTheme).toHaveBeenCalledWith('#7c3aed', 'light'));
    expect(generateTheme).toHaveBeenCalledWith('#7c3aed', 'dark');
  });

  it('previews a button, badge and selected row in light and dark', () => {
    mount();
    for (const name of ['Light preview', 'Dark preview']) {
      const group = screen.getByRole('group', { name });
      expect(within(group).getByRole('button', { name: 'Preview button' })).toBeInTheDocument();
      expect(within(group).getByText('Preview badge')).toBeInTheDocument();
      expect(within(group).getByText('Preview row')).toBeInTheDocument();
    }
    expect(generateTheme).toHaveBeenCalledWith('#3b82f6', 'light');
    expect(generateTheme).toHaveBeenCalledWith('#3b82f6', 'dark');
  });

  it('Save PUTs the chosen preset with a null custom colour and refreshes cached settings', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    const { invalidate } = mount();
    fireEvent.click(radio('Teal'));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/user-management/settings/general');
    expect(init.method).toBe('PUT');
    expect(sentBody()).toEqual({ theme: { preset: 'teal', custom_hex: null } });
    await waitFor(() => expect(invalidate).toHaveBeenCalled());
  });

  it('Save sends a valid custom colour as custom_hex', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    mount();
    fireEvent.change(screen.getByRole('textbox', { name: 'Custom colour' }), { target: { value: '#7c3aed' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const body = sentBody();
    expect(Object.keys(body)).toEqual(['theme']);
    expect(body.theme.custom_hex).toBe('#7c3aed');
    expect(['sorento-blue', 'sorento-red', 'teal', 'graphite', 'indigo']).toContain(body.theme.preset);
  });

  it('Save is disabled for a custom colour that is not #rrggbb and nothing is sent', () => {
    mount();
    const input = screen.getByRole('textbox', { name: 'Custom colour' });
    for (const bad of ['#12345', 'red', '#12345g']) {
      fireEvent.change(input, { target: { value: bad } });
      expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    }
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('Reset to Sorento Blue puts the draft back without saving', async () => {
    mockSettings.theme = { preset: 'teal', customHex: '#7c3aed' };
    mount();
    expect(screen.getByRole('textbox', { name: 'Custom colour' })).toHaveValue('#7c3aed');
    fireEvent.click(screen.getByRole('button', { name: 'Reset to Sorento Blue' }));

    expect(radio('Sorento Blue')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('textbox', { name: 'Custom colour' })).toHaveValue('');
    expect(apiFetch).not.toHaveBeenCalled();

    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    expect(sentBody()).toEqual({ theme: { preset: 'sorento-blue', custom_hex: null } });
  });

  it('a failed save keeps the draft and the form usable', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 403, json: async () => ({ message: 'Forbidden' }) });
    mount();
    fireEvent.click(radio('Graphite'));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).not.toBeDisabled());
    expect(radio('Graphite')).toHaveAttribute('aria-checked', 'true');
  });
});
