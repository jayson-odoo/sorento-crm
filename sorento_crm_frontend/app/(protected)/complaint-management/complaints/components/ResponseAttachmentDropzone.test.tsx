import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { ResponseAttachmentDropzone } from './ResponseAttachmentDropzone';

function file(name: string, size: number, type = 'image/png'): File {
  const blob = new File([new Uint8Array(size)], name, { type });
  return blob;
}

// A thin controlled-state harness - the real popups (ComplaintDetail /
// StockInquiryDetail) hold `files` in local state and pass it straight
// through, so this mirrors the real usage without pulling in either page.
function Harness({ initial = [] as File[], disabled = false }: { initial?: File[]; disabled?: boolean }) {
  const [files, setFiles] = React.useState<File[]>(initial);
  return <ResponseAttachmentDropzone files={files} onFilesChange={setFiles} disabled={disabled} />;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ResponseAttachmentDropzone', () => {
  it('renders empty with no staged files', () => {
    render(<Harness />);
    expect(screen.queryByRole('listitem')).toBeNull();
    expect(screen.getByText(/drop files here/i)).toBeInTheDocument();
  });

  it('stages multiple files via the file picker and shows name + size for each', () => {
    render(<Harness />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const f1 = file('photo.png', 2048);
    const f2 = file('report.pdf', 1024 * 1024, 'application/pdf');

    fireEvent.change(input, { target: { files: [f1, f2] } });

    expect(screen.getByText('photo.png')).toBeInTheDocument();
    expect(screen.getByText('2.0 KB')).toBeInTheDocument();
    expect(screen.getByText('report.pdf')).toBeInTheDocument();
    expect(screen.getByText('1.0 MB')).toBeInTheDocument();
  });

  it('accumulates files across successive selections rather than replacing', () => {
    render(<Harness />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file('a.png', 100)] } });
    fireEvent.change(input, { target: { files: [file('b.png', 200)] } });

    expect(screen.getByText('a.png')).toBeInTheDocument();
    expect(screen.getByText('b.png')).toBeInTheDocument();
  });

  it('removes a staged file when its remove button is clicked', () => {
    render(<Harness initial={[file('keep.png', 100), file('remove-me.png', 200)]} />);
    expect(screen.getByText('remove-me.png')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Remove remove-me.png'));

    expect(screen.queryByText('remove-me.png')).toBeNull();
    expect(screen.getByText('keep.png')).toBeInTheDocument();
  });

  it('does not perform any network call itself - no fetch/apiFetch is ever touched', () => {
    const fetchSpy = vi.fn();
    const originalFetch = globalThis.fetch;
    (globalThis as unknown as { fetch: unknown }).fetch = fetchSpy;

    render(<Harness />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file('a.png', 100)] } });
    fireEvent.click(screen.getByLabelText('Remove a.png'));

    expect(fetchSpy).not.toHaveBeenCalled();
    (globalThis as unknown as { fetch: unknown }).fetch = originalFetch;
  });

  it('disables choose / paste / remove while disabled (e.g. upload in flight)', () => {
    render(<Harness initial={[file('a.png', 100)]} disabled />);
    expect(screen.getByRole('button', { name: /choose file/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /paste from clipboard/i })).toBeDisabled();
    expect(screen.getByLabelText('Remove a.png')).toBeDisabled();
  });

  it('ignores an empty file selection', () => {
    render(<Harness />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [] } });
    expect(screen.queryByRole('listitem')).toBeNull();
  });
});
