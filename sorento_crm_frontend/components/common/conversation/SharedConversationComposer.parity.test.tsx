/**
 * Composer parity: "/" snippets, emoji at the caret, AI assist (UAC AC-L4/L5).
 *
 * Kept apart from `SharedConversationComposer.test.tsx` (the send/window/template
 * suite) because these three features are opt-in props: every surface that does
 * NOT pass them must stay byte-identical, and that is easier to see when the two
 * suites are separate.
 *
 * The emoji BUTTON is stubbed: `emoji-picker-react` behind `next/dynamic` inside
 * a Radix popover proves nothing about our code, and what AC-L5 actually asks
 * for - "inserts at the caret" - is ours. The stub fires the same `onSelect`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { MessageSnippetOption } from '@/app/(protected)/sla-management/message-snippets/types/messageSnippet.types';

const useMessageSnippetOptions = vi.fn();

vi.mock('@/app/(protected)/sla-management/message-snippets/hooks/useMessageSnippets', () => ({
  useMessageSnippetOptions: (...args: unknown[]) => useMessageSnippetOptions(...args),
}));

vi.mock('./EmojiPickerButton', () => ({
  default: ({ onSelect, disabled }: { onSelect: (e: string) => void; disabled?: boolean }) => (
    <button
      type="button"
      data-testid="emoji-picker-trigger"
      disabled={disabled}
      onClick={() => onSelect('🙂')}
    >
      emoji
    </button>
  ),
}));

vi.mock('@/services/whatsappTemplateService', async () => {
  const actual =
    await vi.importActual<typeof import('@/services/whatsappTemplateService')>(
      '@/services/whatsappTemplateService',
    );
  return {
    ...actual,
    getWindowState: vi.fn().mockResolvedValue({
      open: true,
      last_incoming_at: null,
      checked_at: '2026-08-15T00:00:00Z',
    }),
    sendConversationMessage: vi.fn().mockResolvedValue({ sent_as: 'text' }),
    getChatTemplatePreview: vi.fn().mockResolvedValue({ configured: false }),
    listApprovedTemplates: vi.fn().mockResolvedValue([]),
    sendTemplateMessage: vi.fn(),
  };
});

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import SharedConversationComposer from './SharedConversationComposer';
import { toast } from 'sonner';

const SNIPPETS: MessageSnippetOption[] = [
  {
    id: 's1',
    name: 'Stock check',
    shortcut: 'stock',
    body: 'Hi $contact_name, we are checking stock.',
    resolved_body: 'Hi Aisyah Rahman, we are checking stock.',
  },
  {
    id: 's2',
    name: 'Delivery ETA',
    shortcut: 'eta',
    body: 'Your order arrives on $ticket_ref.',
    resolved_body: 'Your order arrives soon. Ref ENQ-4C5D6E.',
  },
];

function snippetQuery(over: Record<string, unknown> = {}) {
  return {
    data: SNIPPETS,
    isLoading: false,
    isError: false,
    error: null,
    ...over,
  };
}

function renderComposer(
  props: Partial<React.ComponentProps<typeof SharedConversationComposer>> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SharedConversationComposer
        entityType="conversation_sla"
        entityId="t1"
        canReply
        mode="conversation"
        showTemplateButton={false}
        {...props}
      />
    </QueryClientProvider>,
  );
}

const input = () => screen.getByPlaceholderText('Type your message...') as HTMLTextAreaElement;

/** jsdom keeps the caret at 0 after a programmatic value change; place it. */
function typeInto(value: string, caret = value.length) {
  const node = input();
  fireEvent.change(node, { target: { value } });
  node.setSelectionRange(caret, caret);
  fireEvent.keyUp(node, { key: 'x' });
}

beforeEach(() => {
  vi.clearAllMocks();
  useMessageSnippetOptions.mockReturnValue(snippetQuery());
});

// ------------------------------------------------------------------ snippets

describe('SharedConversationComposer - snippets (AC-L4)', () => {
  it('offers nothing new when the feature is off', async () => {
    renderComposer();
    await waitFor(() => expect(input()).toBeInTheDocument());

    expect(screen.queryByTestId('snippet-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('emoji-picker-trigger')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ai-assist-button')).not.toBeInTheDocument();

    typeInto('/');
    expect(screen.queryByTestId('snippet-picker')).not.toBeInTheDocument();
  });

  it('opens on a "/" at the start of the input', async () => {
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('/');

    expect(await screen.findByTestId('snippet-picker')).toBeInTheDocument();
    expect(screen.getAllByTestId('snippet-option')).toHaveLength(2);
  });

  it('does not open on a slash mid-sentence', async () => {
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('delivery due 15/08');

    expect(screen.queryByTestId('snippet-picker')).not.toBeInTheDocument();
  });

  it('narrows as the user keeps typing', async () => {
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('/');
    await screen.findByTestId('snippet-picker');
    typeInto('/eta');

    await waitFor(() => expect(screen.getAllByTestId('snippet-option')).toHaveLength(1));
    expect(screen.getByText('Delivery ETA')).toBeInTheDocument();
  });

  it('inserts the RESOLVED body and drops the "/query" that summoned it', async () => {
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('/sto');
    fireEvent.mouseDown(await screen.findByTestId('snippet-option'));

    await waitFor(() =>
      expect(input()).toHaveValue('Hi Aisyah Rahman, we are checking stock.'),
    );
    // The stored `$contact_name` never reaches the box a human sends from.
    expect(input().value).not.toContain('$contact_name');
    expect(screen.queryByTestId('snippet-picker')).not.toBeInTheDocument();
  });

  it('leaves the inserted text editable', async () => {
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('/sto');
    fireEvent.mouseDown(await screen.findByTestId('snippet-option'));
    await waitFor(() => expect(input().value).toContain('Aisyah'));

    fireEvent.change(input(), { target: { value: 'Hi Aisyah, stock confirmed.' } });
    expect(input()).toHaveValue('Hi Aisyah, stock confirmed.');
  });

  it('picks with the keyboard, and Enter chooses instead of sending', async () => {
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('/');
    await screen.findByTestId('snippet-picker');
    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    fireEvent.keyDown(input(), { key: 'Enter' });

    await waitFor(() =>
      expect(input()).toHaveValue('Your order arrives soon. Ref ENQ-4C5D6E.'),
    );
  });

  it('closes on Escape without inserting anything', async () => {
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('/sto');
    await screen.findByTestId('snippet-picker');
    fireEvent.keyDown(input(), { key: 'Escape' });

    await waitFor(() => expect(screen.queryByTestId('snippet-picker')).not.toBeInTheDocument());
    expect(input()).toHaveValue('/sto');
  });

  it('opens from the toolbar button and inserts at the caret', async () => {
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('Hello. ');
    fireEvent.click(screen.getByTestId('snippet-button'));
    const options = await screen.findAllByTestId('snippet-option');
    fireEvent.mouseDown(options[0]);

    await waitFor(() =>
      expect(input()).toHaveValue('Hello. Hi Aisyah Rahman, we are checking stock.'),
    );
  });

  it('asks for the snippets only once the picker opens', async () => {
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    expect(useMessageSnippetOptions).toHaveBeenLastCalledWith('t1', false);

    typeInto('/');

    await waitFor(() => expect(useMessageSnippetOptions).toHaveBeenLastCalledWith('t1', true));
  });

  it('says so when the snippets fail to load', async () => {
    useMessageSnippetOptions.mockReturnValue(
      snippetQuery({ data: [], isError: true, error: new Error('Failed to load snippets') }),
    );
    renderComposer({ snippetsEnabled: true, snippetTrackingId: 't1' });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('/');

    expect(await screen.findByTestId('snippet-picker-error')).toHaveTextContent(
      'Failed to load snippets',
    );
  });
});

// --------------------------------------------------------------------- emoji

describe('SharedConversationComposer - emoji (AC-L5)', () => {
  it('inserts at the caret, not at the end', async () => {
    renderComposer({ emojiEnabled: true });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('Thanks  a lot', 7); // caret between the two spaces
    fireEvent.click(screen.getByTestId('emoji-picker-trigger'));

    await waitFor(() => expect(input()).toHaveValue('Thanks 🙂 a lot'));
  });

  it('appends when the box is empty', async () => {
    renderComposer({ emojiEnabled: true });
    await waitFor(() => expect(input()).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('emoji-picker-trigger'));

    await waitFor(() => expect(input()).toHaveValue('🙂'));
  });
});

// ----------------------------------------------------------------- AI assist

describe('SharedConversationComposer - AI assist (AC-L5)', () => {
  it('writes the draft into the input', async () => {
    const onAiAssist = vi.fn().mockResolvedValue('Your order ships tomorrow.');
    renderComposer({ onAiAssist });
    await waitFor(() => expect(input()).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('ai-assist-button'));

    await waitFor(() => expect(input()).toHaveValue('Your order ships tomorrow.'));
    expect(onAiAssist).toHaveBeenCalledWith({});
  });

  it('treats anything already typed as the instruction, and replaces it', async () => {
    const onAiAssist = vi.fn().mockResolvedValue('Sorry for the wait - Tuesday works.');
    renderComposer({ onAiAssist });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('offer Tuesday delivery');
    fireEvent.click(screen.getByTestId('ai-assist-button'));

    await waitFor(() =>
      expect(onAiAssist).toHaveBeenCalledWith({ instruction: 'offer Tuesday delivery' }),
    );
    // The instruction must NOT survive into the message the customer reads.
    await waitFor(() => expect(input()).toHaveValue('Sorry for the wait - Tuesday works.'));
  });

  it('shows a loading state and refuses a second click while drafting', async () => {
    let release: (value: string) => void = () => {};
    const onAiAssist = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          release = resolve;
        }),
    );
    renderComposer({ onAiAssist });
    await waitFor(() => expect(input()).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('ai-assist-button'));

    await waitFor(() =>
      expect(screen.getByTestId('ai-assist-button')).toHaveTextContent('Drafting'),
    );
    expect(screen.getByTestId('ai-assist-button')).toBeDisabled();
    fireEvent.click(screen.getByTestId('ai-assist-button'));
    expect(onAiAssist).toHaveBeenCalledTimes(1);

    release('done');
    await waitFor(() => expect(input()).toHaveValue('done'));
    expect(screen.getByTestId('ai-assist-button')).toHaveTextContent('AI assist');
  });

  it('toasts the failure and leaves the draft alone', async () => {
    const onAiAssist = vi.fn().mockRejectedValue(new Error('The AI assistant is not configured.'));
    renderComposer({ onAiAssist });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('half a sentence');
    fireEvent.click(screen.getByTestId('ai-assist-button'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('The AI assistant is not configured.'),
    );
    expect(input()).toHaveValue('half a sentence');
    expect(screen.getByTestId('ai-assist-button')).not.toBeDisabled();
  });

  it('treats an empty draft as a failure rather than blanking the box', async () => {
    const onAiAssist = vi.fn().mockResolvedValue('   ');
    renderComposer({ onAiAssist });
    await waitFor(() => expect(input()).toBeInTheDocument());

    typeInto('keep me');
    fireEvent.click(screen.getByTestId('ai-assist-button'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('The assistant returned an empty draft.'),
    );
    expect(input()).toHaveValue('keep me');
  });
});
