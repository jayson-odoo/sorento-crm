/**
 * OUTBOX-ATTACHMENT - the outbox row detail lists every file the email sends, each with a
 * Download (and, for Excel/PDF, a Preview through the shared attachment preview modal).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import EmailOutboxAttachments from './EmailOutboxAttachments';
import { downloadEmailOutboxAttachment } from '../services/emailOutboxService';
import { saveBlobAs } from '@/lib/save-blob';
import { toast } from '@/lib/toast';

vi.mock('../services/emailOutboxService', () => ({
  downloadEmailOutboxAttachment: vi.fn(),
  emailOutboxAttachmentUrl: (rowId: string, index: number) =>
    `/api/v1/system/email-outbox/${rowId}/attachments/${index}`,
}));
vi.mock('@/lib/save-blob', () => ({ saveBlobAs: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const previewProps: { current: Record<string, unknown> | null } = { current: null };
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  default: (props: Record<string, unknown>) => {
    previewProps.current = props;
    return props.open ? <div data-testid="preview-modal" /> : null;
  },
}));

const mockDownload = vi.mocked(downloadEmailOutboxAttachment);
const mockSave = vi.mocked(saveBlobAs);

const ROW = 'row-1';
const FILES = [
  { index: 0, filename: 'PO-0001.pdf' },
  { index: 1, filename: 'OI-2609-0042.xlsx' },
  { index: 2, filename: 'photo-7.png' },
];

describe('EmailOutboxAttachments', () => {
  beforeEach(() => {
    mockDownload.mockReset();
    mockSave.mockReset();
    vi.mocked(toast.error).mockReset();
    previewProps.current = null;
  });

  it('lists every attachment by filename with a Download each', () => {
    render(<EmailOutboxAttachments rowId={ROW} attachments={FILES} />);
    for (const f of FILES) expect(screen.getByText(f.filename)).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /download/i })).toHaveLength(3);
  });

  it('renders nothing when the row has no attachments', () => {
    const { container } = render(<EmailOutboxAttachments rowId={ROW} attachments={[]} />);
    expect(container.textContent).toBe('');
  });

  it('Download fetches that attachment by row and position and saves it under its filename', async () => {
    const blob = new Blob(['PK']);
    mockDownload.mockResolvedValueOnce(blob);
    render(<EmailOutboxAttachments rowId={ROW} attachments={FILES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Download OI-2609-0042.xlsx' }));
    await waitFor(() => expect(mockSave).toHaveBeenCalledWith(blob, 'OI-2609-0042.xlsx'));
    expect(mockDownload).toHaveBeenCalledWith(ROW, 1);
  });

  it('a failed Download toasts the server message', async () => {
    mockDownload.mockRejectedValueOnce(new Error('Attachment file not found in storage'));
    render(<EmailOutboxAttachments rowId={ROW} attachments={FILES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Download OI-2609-0042.xlsx' }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Attachment file not found in storage'),
    );
    expect(mockSave).not.toHaveBeenCalled();
  });

  it('offers Preview for Excel and PDF only', () => {
    render(<EmailOutboxAttachments rowId={ROW} attachments={FILES} />);
    expect(screen.getByRole('button', { name: 'Preview PO-0001.pdf' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Preview OI-2609-0042.xlsx' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Preview photo-7.png' })).toBeNull();
  });

  it('Preview opens the shared preview modal on that file, read through the row route', () => {
    render(<EmailOutboxAttachments rowId={ROW} attachments={FILES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Preview OI-2609-0042.xlsx' }));
    expect(screen.getByTestId('preview-modal')).toBeTruthy();
    const props = previewProps.current as {
      items: { name: string; downloadUrl?: string }[];
      startIndex: number;
    };
    expect(props.items[props.startIndex].name).toBe('OI-2609-0042.xlsx');
    expect(props.items[props.startIndex].downloadUrl).toBe(
      '/api/v1/system/email-outbox/row-1/attachments/1',
    );
    expect(props.items.map((i) => i.name)).not.toContain('photo-7.png');
  });
});
