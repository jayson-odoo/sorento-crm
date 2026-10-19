/**
 * ATTACH-ACCEPT: the portal file picker offers exactly the file types the
 * "Portal Submission" attachment type allows (the form hands down the list
 * from its `/me`), instead of a hard-coded image/video/pdf/txt list that
 * greyed out xlsx and csv. A file the type does not allow is refused at once
 * with the allowed types named.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    uploadAttachment: vi.fn(),
    deleteAttachment: vi.fn(),
  };
});

import { uploadAttachment } from '../lib/portal-client';
import { AttachmentDropzone } from './AttachmentDropzone';

function fileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]');
  if (!input) throw new Error('no file input');
  return input as HTMLInputElement;
}

function pick(input: HTMLInputElement, files: File[]) {
  fireEvent.change(input, { target: { files } });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AttachmentDropzone accept list (portal)', () => {
  it('offers exactly the attachment type allowed extensions in the picker', async () => {
    const { container } = render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[]}
        onChange={vi.fn()}
        allowedExtensions={['csv', 'jpg', 'png', 'xlsx']}
      />,
    );

    await waitFor(() =>
      expect(fileInput(container).getAttribute('accept')).toBe('.csv,.jpg,.png,.xlsx'),
    );
  });

  it('uploads an xlsx and a csv the type allows', async () => {
    vi.mocked(uploadAttachment).mockImplementation(async (_kind, _id, file) => ({
      link_id: `link-${file.name}`,
      attachment_id: `att-${file.name}`,
      filename: file.name,
      size: file.size,
      url: null,
      content_type: file.type,
      uploader_kind: 'contact',
      can_unlink: true,
    }));
    const { container } = render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[]}
        onChange={vi.fn()}
        allowedExtensions={['csv', 'jpg', 'png', 'xlsx']}
      />,
    );
    await waitFor(() => expect(fileInput(container).getAttribute('accept')).toContain('.xlsx'));

    pick(fileInput(container), [
      new File(['x'], 'stock_debt_reserve.xlsx'),
      new File(['x'], 'stock_debt_reserve.csv', { type: 'text/csv' }),
    ]);

    await waitFor(() => expect(uploadAttachment).toHaveBeenCalledTimes(2));
    expect(toasts.error).not.toHaveBeenCalled();
  });

  it('refuses a file the type does not allow and names the allowed types', async () => {
    const { container } = render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[]}
        onChange={vi.fn()}
        allowedExtensions={['csv', 'jpg', 'png', 'xlsx']}
      />,
    );
    await waitFor(() => expect(fileInput(container).getAttribute('accept')).toContain('.xlsx'));

    pick(fileInput(container), [new File(['x'], 'setup.exe')]);

    await waitFor(() => expect(toasts.error).toHaveBeenCalled());
    const message = String(toasts.error.mock.calls[0][0]);
    expect(message).toContain('setup.exe');
    expect(message).toContain('Allowed: csv, jpg, png, xlsx');
    expect(uploadAttachment).not.toHaveBeenCalled();
  });

  it('does not buffer a refused file before the submission exists, but keeps the allowed one', async () => {
    const onPendingFilesChange = vi.fn();
    const { container } = render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId={null}
        attachments={[]}
        onChange={vi.fn()}
        pendingFiles={[]}
        onPendingFilesChange={onPendingFilesChange}
        allowedExtensions={['csv', 'xlsx']}
      />,
    );
    await waitFor(() => expect(fileInput(container).getAttribute('accept')).toContain('.xlsx'));

    const ok = new File(['x'], 'orders.CSV');
    pick(fileInput(container), [new File(['x'], 'photo.heic'), ok]);

    await waitFor(() => expect(onPendingFilesChange).toHaveBeenCalledWith([ok]));
    expect(String(toasts.error.mock.calls[0][0])).toContain('Allowed: csv, xlsx');
  });

  it.each([
    ['not known yet', undefined],
    ['empty (the type sets no limit)', []],
  ])('leaves the picker open to every file when the list is %s', (_label, allowed) => {
    const { container } = render(
      <AttachmentDropzone
        kind="stock_inquiry"
        submissionId="sub-1"
        attachments={[]}
        onChange={vi.fn()}
        allowedExtensions={allowed}
      />,
    );

    // Never a guessed list: the server stays the authority when the type gives none.
    expect(fileInput(container).hasAttribute('accept')).toBe(false);
  });
});
