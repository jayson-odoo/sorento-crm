import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import RespondWorkspacesAdmin from './RespondWorkspacesAdmin';
import type { RespondWorkspace } from '../services/respondWorkspaceService';

/**
 * Chatbot retry ingress config (AC-804, S8a). Same shape as
 * `RespondWorkspacesAdmin.embed.test.tsx`: the dialog is opened via the toolbar
 * "Add workspace" button, since DataGrid row-action buttons don't drive React state
 * reliably under jsdom (that file's own finding). The edit-mode "Key set" display
 * (driven by `has_chatbot_retry_key` on an EXISTING row) is attempted here via the
 * row's Edit button for completeness, but per that same finding it is not the
 * load-bearing assertion for this AC - the backend's `has_chatbot_retry_key` bool
 * contract is proven in `tests/chatbot/test_s8_retry_config.py`, and the rendered
 * edit-mode state is confirmed at browser-verification / Playwright handoff.
 *
 * RED-first: none of this exists on the component yet, so every test here fails on
 * "Unable to find a label with the text of: ..." (`getByLabelText`) or "Unable to
 * find an element with the text: ..." (`getByText`) - never a TypeScript error, since
 * vitest's esbuild transform does not type-check and the mocked service objects
 * carry the new fields as plain extra properties.
 */

const listRespondWorkspaces = vi.fn();
const listIdeationProducts = vi.fn();
const updateRespondWorkspace = vi.fn();
const updateRespondWorkspaceChatbotRetry = vi.fn();
const createRespondWorkspace = vi.fn();
const deleteRespondWorkspace = vi.fn();
const setDefaultRespondWorkspace = vi.fn();

vi.mock('../services/respondWorkspaceService', () => ({
  listRespondWorkspaces: (...a: unknown[]) => listRespondWorkspaces(...a),
  listIdeationProducts: (...a: unknown[]) => listIdeationProducts(...a),
  updateRespondWorkspace: (...a: unknown[]) => updateRespondWorkspace(...a),
  updateRespondWorkspaceChatbotRetry: (...a: unknown[]) =>
    updateRespondWorkspaceChatbotRetry(...a),
  createRespondWorkspace: (...a: unknown[]) => createRespondWorkspace(...a),
  deleteRespondWorkspace: (...a: unknown[]) => deleteRespondWorkspace(...a),
  setDefaultRespondWorkspace: (...a: unknown[]) => setDefaultRespondWorkspace(...a),
}));

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const ROW: RespondWorkspace = {
  id: 'ws-1',
  space_id: '364817',
  name: 'Sorento Main',
  base_url: 'https://api.respond.io',
  whatsapp_number: '60123456789',
  is_active: true,
  is_default: true,
  api_key_masked: '****abcd',
  ideation_shared_service_url: null,
  ideation_product_id: null,
  ideation_intake_api_key_masked: null,
  ideation_embed_connection_id: null,
  ideation_embed_fe_base_url: null,
  ideation_embed_signing_secret_masked: null,
  created_at: '2026-07-20T00:00:00Z',
  updated_at: '2026-07-20T00:00:00Z',
  // AC-804 fields - not yet declared on `RespondWorkspace`, present here as plain
  // extra properties (vitest does not type-check test files against the interface).
  chatbot_retry_ingress_url: 'https://automate-sorento.foundryx.my/webhook/sorento-main-inject',
  has_chatbot_retry_key: true,
} as RespondWorkspace;

beforeEach(() => {
  listRespondWorkspaces.mockReset().mockResolvedValue([ROW]);
  listIdeationProducts.mockReset().mockResolvedValue({ products: [], error: null });
  createRespondWorkspace.mockReset().mockResolvedValue(ROW);
  updateRespondWorkspace.mockReset().mockResolvedValue(ROW);
  updateRespondWorkspaceChatbotRetry.mockReset().mockResolvedValue(ROW);
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());

async function openAddDialog() {
  renderWithClient(<RespondWorkspacesAdmin />);
  await screen.findByRole('button', { name: /add workspace/i });
  fireEvent.click(screen.getByRole('button', { name: /add workspace/i }));
  await waitFor(() =>
    expect(screen.getByText('Ideas embed (iframe SSO)')).toBeInTheDocument(),
  );
}

describe('RespondWorkspacesAdmin - chatbot retry ingress fields', () => {
  it('renders the retry webhook URL field, empty, in the create dialog', async () => {
    await openAddDialog();

    const url = screen.getByLabelText(/Chatbot retry webhook URL/i) as HTMLInputElement;
    expect(url).toBeInTheDocument();
    expect(url.value).toBe('');
  });

  it('renders a write-only retry key field that never shows a stored value', async () => {
    await openAddDialog();

    const key = screen.getByLabelText(/Retry key/i) as HTMLInputElement;
    // Write-only: password type, so the browser never echoes plaintext (AC-804: "a
    // GET never echoes the key" applies to the FE rendering it too).
    expect(key.type).toBe('password');
    expect(key.value).toBe('');
  });

  it('the retry webhook URL and key fields are editable', async () => {
    await openAddDialog();

    const url = screen.getByLabelText(/Chatbot retry webhook URL/i) as HTMLInputElement;
    fireEvent.change(url, {
      target: { value: 'https://automate-sorento.foundryx.my/webhook/sorento-main-inject' },
    });
    expect(url.value).toBe(
      'https://automate-sorento.foundryx.my/webhook/sorento-main-inject',
    );

    const key = screen.getByLabelText(/Retry key/i) as HTMLInputElement;
    fireEvent.change(key, { target: { value: 'a-fresh-retry-key' } });
    expect(key.value).toBe('a-fresh-retry-key');
  });

  it('an existing workspace with a stored key shows a "Key set" state, never the value', async () => {
    renderWithClient(<RespondWorkspacesAdmin />);
    await screen.findByRole('button', { name: /edit/i });
    fireEvent.click(screen.getByRole('button', { name: /edit/i }));

    await waitFor(() =>
      expect(screen.getByText('Ideas embed (iframe SSO)')).toBeInTheDocument(),
    );

    expect(screen.getByText(/Key set/i)).toBeInTheDocument();
    const key = screen.getByLabelText(/Retry key/i) as HTMLInputElement;
    expect(key.value).toBe('');
    expect(document.body.textContent).not.toMatch(
      /automate-sorento\.foundryx\.my\/webhook\/sorento-main-inject/,
    );
  });

  it('blanking the URL sends an empty string, which is what turns Retry off', async () => {
    // S8a review S2: the field's own copy promises "Leave blank to turn Retry off". The
    // body used to send `null` for a blank field, and null means "no change" on the
    // backend, so the stored URL survived and Retry could not be disabled at all.
    renderWithClient(<RespondWorkspacesAdmin />);
    await screen.findByRole('button', { name: /edit/i });
    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    await waitFor(() =>
      expect(screen.getByText('Ideas embed (iframe SSO)')).toBeInTheDocument(),
    );

    const url = screen.getByLabelText(/Chatbot retry webhook URL/i) as HTMLInputElement;
    expect(url.value).toBe(ROW.chatbot_retry_ingress_url);
    fireEvent.change(url, { target: { value: '  ' } });
    fireEvent.click(screen.getByRole('button', { name: /^update$/i }));

    await waitFor(() => expect(updateRespondWorkspaceChatbotRetry).toHaveBeenCalled());
    const [, retryBody] = updateRespondWorkspaceChatbotRetry.mock.calls[0];
    expect(retryBody.chatbot_retry_ingress_url).toBe('');
    // The key was neither typed nor explicitly removed, so it is not mentioned at all.
    expect('chatbot_retry_ingress_key' in retryBody).toBe(false);
    // And the row PUT is not sent AT ALL, because no field it carries changed
    // (security review round 2). That route keeps its own stronger slug, so sending it
    // unconditionally 403'd a principal holding only `user_management.settings.edit` on
    // the way in and they never reached the narrow retry route AC-804 gave them.
    expect(updateRespondWorkspace).not.toHaveBeenCalled();
  });

  it('clearing the URL to an EMPTY string still sends "", the way the browser does it', async () => {
    // Browser evidence run, 6 Sep 2026: blanking the field and pressing Update left the
    // stored URL in place. The sibling test above blanks to whitespace, which is not the
    // same keystroke sequence a person makes: an operator selects the value and deletes
    // it, so the input goes to "" exactly. This is that.
    renderWithClient(<RespondWorkspacesAdmin />);
    await screen.findByRole('button', { name: /edit/i });
    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    await waitFor(() =>
      expect(screen.getByText('Ideas embed (iframe SSO)')).toBeInTheDocument(),
    );

    const url = screen.getByLabelText(/Chatbot retry webhook URL/i) as HTMLInputElement;
    fireEvent.change(url, { target: { value: '' } });
    expect(url.value).toBe('');
    fireEvent.click(screen.getByRole('button', { name: /^update$/i }));

    await waitFor(() => expect(updateRespondWorkspaceChatbotRetry).toHaveBeenCalled());
    const [, retryBody] = updateRespondWorkspaceChatbotRetry.mock.calls[0];
    expect(retryBody.chatbot_retry_ingress_url).toBe('');
  });

  it('clearing the URL AND removing the key sends both blanks in one retry PUT', async () => {
    // The exact sequence the evidence run drove: the key went out as "" and the URL did
    // not. Both belong to one route and one save, so both have to travel.
    renderWithClient(<RespondWorkspacesAdmin />);
    await screen.findByRole('button', { name: /edit/i });
    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    await waitFor(() =>
      expect(screen.getByText('Ideas embed (iframe SSO)')).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole('button', { name: /remove stored key/i }));
    const url = screen.getByLabelText(/Chatbot retry webhook URL/i) as HTMLInputElement;
    fireEvent.change(url, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /^update$/i }));

    await waitFor(() => expect(updateRespondWorkspaceChatbotRetry).toHaveBeenCalled());
    const [, retryBody] = updateRespondWorkspaceChatbotRetry.mock.calls[0];
    expect(retryBody.chatbot_retry_ingress_url).toBe('');
    expect(retryBody.chatbot_retry_ingress_key).toBe('');
  });

  it('"Remove stored key" is what revokes the key, and it sends an explicit blank', async () => {
    renderWithClient(<RespondWorkspacesAdmin />);
    await screen.findByRole('button', { name: /edit/i });
    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    await waitFor(() =>
      expect(screen.getByText('Ideas embed (iframe SSO)')).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole('button', { name: /remove stored key/i }));
    expect(screen.getByText(/will be removed when you save/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^update$/i }));

    await waitFor(() => expect(updateRespondWorkspaceChatbotRetry).toHaveBeenCalled());
    const [, retryBody] = updateRespondWorkspaceChatbotRetry.mock.calls[0];
    expect(retryBody.chatbot_retry_ingress_key).toBe('');
  });
});
