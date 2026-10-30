/**
 * QUOTE-SEND-WHATSAPP: the prompt that opens a wa.me link for a sent quotation revision.
 * Written to UAC sections B, C, D and F before the component exists.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  QuotationDocument,
  QuotationIssue,
} from '../../../../_shared/services/quotationDocumentService';
import { waMeUrl } from '@/lib/wa-me';

vi.mock('@/lib/toast', () => ({
  toast: { custom: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));

const copyTextToClipboard = vi.fn();
vi.mock('@/lib/clipboard', () => ({
  copyTextToClipboard: (...args: unknown[]) => copyTextToClipboard(...args),
}));

const createQuotationSignLink = vi.fn();
const logQuotationWhatsAppOpened = vi.fn();

vi.mock('../../../../_shared/services/quotationDocumentService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../../_shared/services/quotationDocumentService')
  >();
  return {
    ...actual,
    createQuotationSignLink: (...args: unknown[]) => createQuotationSignLink(...args),
    logQuotationWhatsAppOpened: (...args: unknown[]) => logQuotationWhatsAppOpened(...args),
  };
});

import { toast } from '@/lib/toast';
import { QuotationWhatsAppDialog } from './QuotationWhatsAppDialog';

const document_ = {
  id: 'd1',
  project_id: 'p1',
  document_no: 'PRJQ-2026-0003',
  our_ref: 'PRJQ-2026-0003',
  recipient_phone_snapshot: '03-0000 0001\n012-000 0001',
  attn_name: 'ATTN A',
  subject_title: 'SUBJECT A',
  signatory_name: 'SALES REP A',
} as unknown as QuotationDocument;

const issue = {
  id: 'i2',
  document_id: 'd1',
  issue_no: 2,
  our_ref_text: 'PRJQ-2026-0003 (R2)',
} as unknown as QuotationIssue;

const LINK = () => `${window.location.origin}/quotation-sign/tok123`;

const expectedMessage = () =>
  [
    'Hi ATTN A,',
    '',
    'Here is our quotation PRJQ-2026-0003 (R2) for SUBJECT A.',
    'You can view and accept it here:',
    LINK(),
    '',
    'Thank you,',
    'SALES REP A',
  ].join('\n');

function renderDialog(overrides: { document?: QuotationDocument } = {}) {
  const onOpenChange = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <QuotationWhatsAppDialog
        projectId="p1"
        document={overrides.document ?? document_}
        issue={issue}
        onOpenChange={onOpenChange}
      />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

const openLink = () => screen.getByText('Open WhatsApp').closest('a') as HTMLAnchorElement;

beforeEach(() => {
  vi.clearAllMocks();
  createQuotationSignLink.mockResolvedValue({
    token: 'tok123',
    path: '/quotation-sign/tok123',
    expires_at: null,
  });
  logQuotationWhatsAppOpened.mockResolvedValue(undefined);
  copyTextToClipboard.mockResolvedValue(true);
});

describe('QuotationWhatsAppDialog', () => {
  it('titles the prompt with the revision and mints the link once on open (AC-B1, B2)', async () => {
    renderDialog();
    expect(await screen.findByText('Send R2 via WhatsApp')).toBeInTheDocument();
    await waitFor(() => expect(createQuotationSignLink).toHaveBeenCalledTimes(1));
    expect(createQuotationSignLink).toHaveBeenCalledWith('p1', 'd1', 'i2');
  });

  it('prefills To with the first mobile and Message with the template (AC-C1, D1)', async () => {
    renderDialog();
    const to = await screen.findByLabelText('To');
    expect(to).toHaveValue('+60120000001');
    const message = (await screen.findByLabelText('Message')) as HTMLTextAreaElement;
    await waitFor(() => expect(message.value).toBe(expectedMessage()));
  });

  it('leaves To empty when the quotation holds no mobile (AC-C4)', async () => {
    renderDialog({
      document: { ...document_, recipient_phone_snapshot: '03-0000 0001' } as QuotationDocument,
    });
    expect(await screen.findByLabelText('To')).toHaveValue('');
  });

  it('links Open WhatsApp to wa.me with the digits and the box text, in a new tab (AC-B6)', async () => {
    renderDialog();
    const message = (await screen.findByLabelText('Message')) as HTMLTextAreaElement;
    await waitFor(() => expect(message.value).toBe(expectedMessage()));
    const link = await screen.findByRole('link', { name: 'Open WhatsApp' });
    expect(link).toHaveAttribute('href', waMeUrl('60120000001', expectedMessage()));
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('follows an edited message (AC-B5)', async () => {
    const user = userEvent.setup();
    renderDialog();
    const message = (await screen.findByLabelText('Message')) as HTMLTextAreaElement;
    await waitFor(() => expect(message.value).toBe(expectedMessage()));
    await user.clear(message);
    await user.type(message, 'Custom & text');
    expect(await screen.findByRole('link', { name: 'Open WhatsApp' })).toHaveAttribute(
      'href',
      waMeUrl('60120000001', 'Custom & text'),
    );
  });

  it('cleans a typed local number the same way (AC-B4, B6)', async () => {
    const user = userEvent.setup();
    renderDialog();
    const to = await screen.findByLabelText('To');
    await user.clear(to);
    await user.type(to, '012-000 0001');
    const link = await screen.findByRole('link', { name: 'Open WhatsApp' });
    expect((link as HTMLAnchorElement).getAttribute('href')).toBe(
      waMeUrl('60120000001', (screen.getByLabelText('Message') as HTMLTextAreaElement).value),
    );
  });

  it('uses the number-less wa.me form when To is cleared', async () => {
    const user = userEvent.setup();
    renderDialog();
    const to = await screen.findByLabelText('To');
    await user.clear(to);
    const link = await screen.findByRole('link', { name: 'Open WhatsApp' });
    expect((link as HTMLAnchorElement).getAttribute('href')!.startsWith('https://wa.me/?text=')).toBe(
      true,
    );
  });

  it('is inert while the link is being minted (AC-B3)', async () => {
    createQuotationSignLink.mockReturnValue(new Promise(() => {}));
    renderDialog();
    await screen.findByText('Send R2 via WhatsApp');
    const link = openLink();
    expect(link).toHaveAttribute('aria-disabled', 'true');
    expect(link).not.toHaveAttribute('href');
    expect(screen.getByRole('button', { name: 'Copy link' })).toBeDisabled();
  });

  it('says so and stays inert when minting fails (AC-B3)', async () => {
    createQuotationSignLink.mockRejectedValue(new Error('boom'));
    renderDialog();
    expect(await screen.findByText('Could not create the counter-sign link.')).toBeInTheDocument();
    const link = openLink();
    expect(link).toHaveAttribute('aria-disabled', 'true');
    expect(link).not.toHaveAttribute('href');
    expect(screen.getByRole('button', { name: 'Copy link' })).toBeDisabled();
  });

  it('logs the open once with project, document and issue (AC-F1)', async () => {
    renderDialog();
    const link = await screen.findByRole('link', { name: 'Open WhatsApp' });
    // Stop jsdom navigating; the click handler still runs.
    link.addEventListener('click', (e) => e.preventDefault());
    fireEvent.click(link);
    await waitFor(() => expect(logQuotationWhatsAppOpened).toHaveBeenCalledTimes(1));
    expect(logQuotationWhatsAppOpened).toHaveBeenCalledWith('p1', 'd1', 'i2');
  });

  it('shows no error toast when the log call fails (AC-F3)', async () => {
    logQuotationWhatsAppOpened.mockRejectedValue(new Error('nope'));
    renderDialog();
    const link = await screen.findByRole('link', { name: 'Open WhatsApp' });
    link.addEventListener('click', (e) => e.preventDefault());
    fireEvent.click(link);
    await waitFor(() => expect(logQuotationWhatsAppOpened).toHaveBeenCalledTimes(1));
    await new Promise((r) => setTimeout(r, 20));
    expect(toast.error).not.toHaveBeenCalled();
  });

  // --- fix round 1 ---

  async function readMessage(document?: QuotationDocument) {
    renderDialog(document ? { document } : {});
    const message = (await screen.findByLabelText('Message')) as HTMLTextAreaElement;
    await waitFor(() => expect(message.value).not.toBe(''));
    return message;
  }

  it('signs off with the signed-in signer when the quotation names no signatory (AC-D1)', async () => {
    const message = await readMessage({
      ...document_,
      signatory_name: null,
      signatory_signature: { signer_name: 'SALES REP A' },
    } as unknown as QuotationDocument);
    expect(message.value.endsWith('Thank you,\nSALES REP A')).toBe(true);
  });

  it('prefers the named signatory over the signer (AC-D1)', async () => {
    const message = await readMessage({
      ...document_,
      signatory_name: 'SIGNATORY A',
      signatory_signature: { signer_name: 'SALES REP A' },
    } as unknown as QuotationDocument);
    expect(message.value.endsWith('Thank you,\nSIGNATORY A')).toBe(true);
  });

  it('ends at "Thank you," when neither signatory nor signer is known (AC-D1)', async () => {
    const message = await readMessage({
      ...document_,
      signatory_name: '  ',
      signatory_signature: { signer_name: ' ' },
    } as unknown as QuotationDocument);
    expect(message.value.endsWith('Thank you,')).toBe(true);
  });

  it('selects the link and asks for a manual copy when copying fails (AC-B7)', async () => {
    copyTextToClipboard.mockResolvedValue(false);
    const user = userEvent.setup();
    const message = await readMessage();
    await user.click(screen.getByRole('button', { name: 'Copy link' }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Press Ctrl/Cmd+C to copy the selected link'),
    );
    expect(document.activeElement).toBe(message);
    const start = message.value.indexOf(LINK());
    expect(message.selectionStart).toBe(start);
    expect(message.selectionEnd).toBe(start + LINK().length);
  });

  it('ticks and raises no toast when copying works (AC-B7)', async () => {
    const user = userEvent.setup();
    await readMessage();
    await user.click(screen.getByRole('button', { name: 'Copy link' }));
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument();
    expect(copyTextToClipboard).toHaveBeenCalledWith(LINK());
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.warning).not.toHaveBeenCalled();
    expect(toast.custom).not.toHaveBeenCalled();
  });

  it('mints the link once under StrictMode (AC-B9)', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <React.StrictMode>
        <QueryClientProvider client={client}>
          <QuotationWhatsAppDialog
            projectId="p1"
            document={document_}
            issue={issue}
            onOpenChange={vi.fn()}
          />
        </QueryClientProvider>
      </React.StrictMode>,
    );
    const message = (await screen.findByLabelText('Message')) as HTMLTextAreaElement;
    await waitFor(() => expect(message.value).not.toBe(''));
    expect(createQuotationSignLink).toHaveBeenCalledTimes(1);
  });

  it('starts from the template again after close and reopen (AC-B5)', async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const tree = (open: QuotationIssue | null) => (
      <QueryClientProvider client={client}>
        <QuotationWhatsAppDialog
          projectId="p1"
          document={document_}
          issue={open}
          onOpenChange={vi.fn()}
        />
      </QueryClientProvider>
    );
    const { rerender } = render(tree(issue));
    const first = (await screen.findByLabelText('Message')) as HTMLTextAreaElement;
    await waitFor(() => expect(first.value).toBe(expectedMessage()));
    await user.clear(first);
    await user.type(first, 'Edited text');
    rerender(tree(null));
    await waitFor(() => expect(screen.queryByLabelText('Message')).toBeNull());
    rerender(tree(issue));
    const again = (await screen.findByLabelText('Message')) as HTMLTextAreaElement;
    await waitFor(() => expect(again.value).toBe(expectedMessage()));
  });

  it('shows the link in the fallback dialog when copying fails and the message has no link (AC-B7)', async () => {
    copyTextToClipboard.mockResolvedValue(false);
    const user = userEvent.setup();
    const message = await readMessage();
    await user.clear(message);
    await user.type(message, 'No link here');
    await user.click(screen.getByRole('button', { name: 'Copy link' }));
    const shown = (await screen.findByLabelText('Counter-sign link')) as HTMLInputElement;
    expect(shown.value).toBe(LINK());
    expect(toast.error).not.toHaveBeenCalledWith('Press Ctrl/Cmd+C to copy the selected link');
  });
});
