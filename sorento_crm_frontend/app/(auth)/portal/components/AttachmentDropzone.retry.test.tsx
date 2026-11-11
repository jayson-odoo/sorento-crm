/**
 * UIUX-QUICK-WINS item 8: a failed upload stays on screen as its own row, naming the file and
 * why, with "Try again"; the other files of the same pick still upload. One shared dropzone,
 * so every upload screen gets it (owner rule: one image pipeline).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return { ...original, uploadAttachment: vi.fn(), deleteAttachment: vi.fn() };
});
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { uploadAttachment } from '../lib/portal-client';
import { toast } from '@/lib/toast';
import { AttachmentDropzone } from './AttachmentDropzone';

const upload = uploadAttachment as unknown as ReturnType<typeof vi.fn>;

function att(name: string) {
  return {
    link_id: `link-${name}`,
    attachment_id: `att-${name}`,
    filename: name,
    size: 10,
    url: `https://cdn.example.com/${name}`,
    content_type: 'image/png',
    uploader_kind: 'contact',
    can_unlink: true,
  };
}

beforeEach(() => vi.clearAllMocks());

/** The parent owns the list, as every real screen does. */
function Controlled({ onChange }: { onChange: (next: unknown[]) => void }) {
  const [list, setList] = React.useState<ReturnType<typeof att>[]>([]);
  return (
    <AttachmentDropzone
      kind="stock_inquiry"
      submissionId="s1"
      attachments={list as never}
      onChange={(next) => {
        onChange(next);
        setList(next as never);
      }}
    />
  );
}

describe('AttachmentDropzone upload failure', () => {
  it('shows the failed file with its reason and Try again, and the retry uploads it', async () => {
    const onChange = vi.fn();
    upload.mockImplementation(async (_kind: string, _id: string, file: File) => {
      if (file.name === 'b.png') throw new Error('The file is larger than 10 MB.');
      return att(file.name);
    });
    const { container } = render(<Controlled onChange={onChange} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['a'], 'a.png', { type: 'image/png' }), new File(['b'], 'b.png', { type: 'image/png' })] },
    });

    const row = await screen.findByTestId('upload-failed-b.png');
    expect(row).toHaveTextContent('b.png');
    expect(row).toHaveTextContent('The file is larger than 10 MB.');
    expect(onChange).toHaveBeenLastCalledWith([expect.objectContaining({ filename: 'a.png' })]);
    expect(toast.error).not.toHaveBeenCalled();

    upload.mockImplementation(async (_kind: string, _id: string, file: File) => att(file.name));
    fireEvent.click(screen.getByRole('button', { name: 'Try again: b.png' }));
    await waitFor(() => expect(screen.queryByTestId('upload-failed-b.png')).toBeNull());
    expect(upload).toHaveBeenCalledTimes(3);
    expect(onChange).toHaveBeenLastCalledWith([
      expect.objectContaining({ filename: 'a.png' }),
      expect.objectContaining({ filename: 'b.png' }),
    ]);
  });

  it('a failed row can be dismissed without retrying', async () => {
    upload.mockRejectedValue(new Error('Network error'));
    const { container } = render(
      <AttachmentDropzone kind="stock_inquiry" submissionId="s1" attachments={[]} onChange={vi.fn()} />,
    );
    fireEvent.change(container.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(['c'], 'c.png', { type: 'image/png' })] },
    });
    await screen.findByTestId('upload-failed-c.png');
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss: c.png' }));
    expect(screen.queryByTestId('upload-failed-c.png')).toBeNull();
  });
});
