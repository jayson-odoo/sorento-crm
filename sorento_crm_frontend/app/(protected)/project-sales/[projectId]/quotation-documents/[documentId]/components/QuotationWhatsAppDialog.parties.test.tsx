/**
 * PS-REGISTRATION-V3 rules 10-13 (owner 2 Nov ~21:20): the WhatsApp send picks one of the
 * project's parties (or a person registered at it); a pick with no number takes a typed one and
 * Open WhatsApp saves it to that party or person. A number on file is never overwritten.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  QuotationDocument,
  QuotationIssue,
} from '../../../../_shared/services/quotationDocumentService';

vi.mock('@/lib/toast', () => ({
  toast: { custom: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));

vi.mock('@/lib/clipboard', () => ({ copyTextToClipboard: vi.fn(async () => true) }));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="" />
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
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

const getPartiesOnProject = vi.fn();
const fillPartyPhone = vi.fn();
vi.mock('../../../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../_shared/services/projectService')>();
  return {
    ...actual,
    getPartiesOnProject: (...args: unknown[]) => getPartiesOnProject(...args),
    fillPartyPhone: (...args: unknown[]) => fillPartyPhone(...args),
  };
});

import { QuotationWhatsAppDialog, recipientsOf } from './QuotationWhatsAppDialog';

const document_ = {
  id: 'd1',
  project_id: 'p1',
  document_no: 'PRJQ-2026-0003',
  recipient_phone_snapshot: null,
  attn_name: 'ATTN A',
  subject_title: 'SUBJECT A',
  signatory_name: 'SALES REP A',
} as unknown as QuotationDocument;

const issue = { id: 'i2', document_id: 'd1', issue_no: 2 } as unknown as QuotationIssue;

const PARTIES = [
  {
    party_id: 'dev1',
    party_type: 'developer',
    role: 'developer',
    name: 'Pembangunan Contoh',
    phone: '+60 120000000',
    contacts: [],
  },
  {
    party_id: 'mc1',
    party_type: 'main_contractor',
    role: 'main_contractor',
    name: 'Binaan Sampel',
    phone: null,
    contacts: [
      {
        stakeholder_id: 'st2',
        party_contact_id: 'k2',
        name: 'Example Two',
        job_title: 'QS',
        phone: '+60130000222',
        email: null,
      },
      {
        stakeholder_id: 'st3',
        party_contact_id: 'k3',
        name: 'Example Three',
        job_title: 'PM',
        phone: null,
        email: null,
      },
    ],
  },
];

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <QuotationWhatsAppDialog projectId="p1" document={document_} issue={issue} onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

const sendTo = () => screen.getByLabelText('Send to') as HTMLSelectElement;
const toBox = () => screen.getByLabelText('To') as HTMLInputElement;
const openLink = () => screen.getByText('Open WhatsApp').closest('a') as HTMLAnchorElement;

beforeEach(() => {
  vi.clearAllMocks();
  createQuotationSignLink.mockResolvedValue({ token: 't', path: '/quotation-sign/t', expires_at: null });
  logQuotationWhatsAppOpened.mockResolvedValue(undefined);
  getPartiesOnProject.mockResolvedValue(PARTIES);
  fillPartyPhone.mockResolvedValue({ party_id: 'mc1', stakeholder_id: 'st3', phone: '+60140000333' });
});

describe('QuotationWhatsAppDialog: send to a party of the project', () => {
  it('lists every party and every person registered at it', () => {
    expect(recipientsOf(PARTIES as never).map((r) => r.label)).toEqual([
      'Pembangunan Contoh (Developer)',
      'Binaan Sampel (Main contractor)',
      'Example Two, Binaan Sampel',
      'Example Three, Binaan Sampel',
    ]);
  });

  it('picking a person with a number fills To with it', async () => {
    renderDialog();
    await waitFor(() => expect(sendTo().options.length).toBe(5));
    fireEvent.change(sendTo(), { target: { value: 'person:st2' } });
    expect(toBox().value).toBe('+60130000222');
  });

  it('a pick with no number says so, and the typed number is saved to that person on open', async () => {
    renderDialog();
    await waitFor(() => expect(sendTo().options.length).toBe(5));
    fireEvent.change(sendTo(), { target: { value: 'person:st3' } });
    expect(toBox().value).toBe('');
    expect(screen.getByText(/No number on file/)).toBeInTheDocument();
    fireEvent.change(toBox(), { target: { value: '+60140000333' } });
    await waitFor(() => expect(openLink()).not.toHaveAttribute('aria-disabled'));
    fireEvent.click(openLink());
    await waitFor(() =>
      expect(fillPartyPhone).toHaveBeenCalledWith('p1', 'mc1', {
        phone: '+60140000333',
        stakeholder_id: 'st3',
      }),
    );
  });

  it('a party with no line of its own saves the typed number to the party', async () => {
    renderDialog();
    await waitFor(() => expect(sendTo().options.length).toBe(5));
    fireEvent.change(sendTo(), { target: { value: 'party:main_contractor:mc1' } });
    fireEvent.change(toBox(), { target: { value: '0130000000' } });
    await waitFor(() => expect(openLink()).not.toHaveAttribute('aria-disabled'));
    fireEvent.click(openLink());
    await waitFor(() =>
      expect(fillPartyPhone).toHaveBeenCalledWith('p1', 'mc1', {
        phone: '+60130000000', // saved normalised, as WhatsApp dialled it
        stakeholder_id: null,
      }),
    );
  });

  it('never saves over a number already on file, even when To was edited', async () => {
    renderDialog();
    await waitFor(() => expect(sendTo().options.length).toBe(5));
    fireEvent.change(sendTo(), { target: { value: 'person:st2' } });
    fireEvent.change(toBox(), { target: { value: '+60139999999' } });
    await waitFor(() => expect(openLink()).not.toHaveAttribute('aria-disabled'));
    fireEvent.click(openLink());
    await waitFor(() => expect(logQuotationWhatsAppOpened).toHaveBeenCalled());
    expect(fillPartyPhone).not.toHaveBeenCalled();
  });

  it('a typed number with no party picked saves nothing (the free To still works)', async () => {
    renderDialog();
    await waitFor(() => expect(sendTo().options.length).toBe(5));
    fireEvent.change(toBox(), { target: { value: '+60120000000' } });
    await waitFor(() => expect(openLink()).not.toHaveAttribute('aria-disabled'));
    fireEvent.click(openLink());
    await waitFor(() => expect(logQuotationWhatsAppOpened).toHaveBeenCalled());
    expect(fillPartyPhone).not.toHaveBeenCalled();
  });

  it('titles a lettered proposal revision by its label, else R<n> (#2097)', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <QuotationWhatsAppDialog
          projectId="p1"
          document={document_}
          issue={{ ...issue, revision_label: 'B' } as unknown as QuotationIssue}
          onOpenChange={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Send rev B to the customer via WhatsApp')).toBeInTheDocument();
  });
});
