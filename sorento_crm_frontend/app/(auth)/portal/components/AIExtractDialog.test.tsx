import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { AIExtractDialog, AIExtractApplyPayload } from './AIExtractDialog';

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    aiExtractFromFiles: vi.fn(),
  };
});

import {
  aiExtractFromFiles,
  AIExtractResult,
} from '../lib/portal-client';

// Mocked so the test asserts on the exact `open` / `items` props the dialog
// hands the shared modal ("previews in place") without pulling in the carousel
// engine (embla needs layout APIs jsdom lacks).
const previewPropsSpy = vi.fn();
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: (props: {
    open: boolean;
    items: { id: string; name: string; url: string }[];
    startIndex?: number;
  }) => {
    previewPropsSpy(props);
    if (!props.open) return null;
    return (
      <div data-testid="preview-modal">
        {props.items.map((it) => (
          <span key={it.id}>{it.name}</span>
        ))}
        <span data-testid="preview-start-index">{props.startIndex ?? 0}</span>
      </div>
    );
  },
}));

const FIELD_DEFS = [
  { name: 'customer_name', label: 'Customer name' },
  { name: 'product_code', label: 'Product code' },
  { name: 'within_warranty', label: 'Within warranty' },
];

function renderDialog(onApply: (p: AIExtractApplyPayload) => void) {
  return render(
    <AIExtractDialog
      open
      onOpenChange={() => {}}
      kind="complaint"
      fieldDefs={FIELD_DEFS}
      onApply={onApply}
    />,
  );
}

function makeFile(name: string, type = 'image/png', content = 'x'): File {
  return new File([content], name, { type });
}

const mockExtractResult: AIExtractResult = {
  values: {
    customer_name: 'ACME Sdn Bhd',
    product_code: 'AB-1234',
    within_warranty: 'Yes',
  },
  products: [],
  per_field: {},
  usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
  model: 'gpt-4o',
  provider: 'openai',
};

describe('AIExtractDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('runs extract and shows the review stage with all fields', async () => {
    (aiExtractFromFiles as ReturnType<typeof vi.fn>).mockResolvedValue(mockExtractResult);
    const onApply = vi.fn();
    renderDialog(onApply);

    const input = screen.getByTestId('ai-extract-file-input') as HTMLInputElement;
    Object.defineProperty(input, 'files', {
      value: [makeFile('do.png')],
      writable: false,
    });
    fireEvent.change(input);

    fireEvent.click(screen.getByTestId('ai-extract-run'));

    await waitFor(() => screen.getByTestId('ai-extract-review'));
    expect(screen.getByTestId('ai-extract-field-customer_name')).toBeInTheDocument();
    expect(screen.getByTestId('ai-extract-field-product_code')).toBeInTheDocument();
    expect(screen.getByTestId('ai-extract-field-within_warranty')).toBeInTheDocument();
    expect(aiExtractFromFiles).toHaveBeenCalledWith(
      'portal.complaint',
      [expect.any(File)],
    );
  });

  it('drops a field when × is clicked and excludes it on confirm', async () => {
    (aiExtractFromFiles as ReturnType<typeof vi.fn>).mockResolvedValue(mockExtractResult);
    const onApply = vi.fn();
    renderDialog(onApply);

    const input = screen.getByTestId('ai-extract-file-input') as HTMLInputElement;
    Object.defineProperty(input, 'files', {
      value: [makeFile('do.png')],
      writable: false,
    });
    fireEvent.change(input);
    fireEvent.click(screen.getByTestId('ai-extract-run'));

    await waitFor(() => screen.getByTestId('ai-extract-review'));
    fireEvent.click(screen.getByTestId('ai-extract-drop-product_code'));
    expect(screen.queryByTestId('ai-extract-field-product_code')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('ai-extract-confirm'));
    expect(onApply).toHaveBeenCalledTimes(1);
    const payload = onApply.mock.calls[0][0] as AIExtractApplyPayload;
    expect(payload.values).toEqual({
      customer_name: 'ACME Sdn Bhd',
      within_warranty: 'Yes',
    });
    expect(payload.alsoAttach).toBe(true);
    expect(payload.files).toHaveLength(1);
  });

  it('passes alsoAttach=false when checkbox is toggled off', async () => {
    (aiExtractFromFiles as ReturnType<typeof vi.fn>).mockResolvedValue(mockExtractResult);
    const onApply = vi.fn();
    renderDialog(onApply);

    const input = screen.getByTestId('ai-extract-file-input') as HTMLInputElement;
    Object.defineProperty(input, 'files', {
      value: [makeFile('do.png')],
      writable: false,
    });
    fireEvent.change(input);
    fireEvent.click(screen.getByTestId('ai-extract-run'));

    await waitFor(() => screen.getByTestId('ai-extract-review'));
    fireEvent.click(screen.getByTestId('ai-extract-attach'));
    fireEvent.click(screen.getByTestId('ai-extract-confirm'));

    const payload = onApply.mock.calls[0][0] as AIExtractApplyPayload;
    expect(payload.alsoAttach).toBe(false);
  });

  it('converts a pasted text block into a .txt file for extraction', async () => {
    (aiExtractFromFiles as ReturnType<typeof vi.fn>).mockResolvedValue(mockExtractResult);
    renderDialog(vi.fn());

    const pasteEvent = new Event('paste', { bubbles: true, cancelable: true }) as Event & {
      clipboardData: unknown;
    };
    pasteEvent.clipboardData = {
      items: [],
      getData: (t: string) => (t === 'text/plain' ? 'Customer: ACME, product AB-1234' : ''),
    };
    fireEvent(window, pasteEvent);

    fireEvent.click(screen.getByTestId('ai-extract-run'));
    await waitFor(() => screen.getByTestId('ai-extract-review'));

    const call = (aiExtractFromFiles as ReturnType<typeof vi.fn>).mock.calls[0];
    const files = call[1] as File[];
    expect(files).toHaveLength(1);
    expect(files[0].name).toMatch(/\.txt$/);
    expect(files[0].type).toBe('text/plain');
  });

  it('surfaces extract errors on the upload stage', async () => {
    (aiExtractFromFiles as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('AI provider call failed: 502'),
    );
    const onApply = vi.fn();
    renderDialog(onApply);

    const input = screen.getByTestId('ai-extract-file-input') as HTMLInputElement;
    Object.defineProperty(input, 'files', {
      value: [makeFile('do.png')],
      writable: false,
    });
    fireEvent.change(input);
    fireEvent.click(screen.getByTestId('ai-extract-run'));

    await waitFor(() => screen.getByTestId('ai-extract-error'));
    expect(screen.getByTestId('ai-extract-error').textContent).toContain('AI provider call failed');
    expect(onApply).not.toHaveBeenCalled();
  });
});

/**
 * Portal attachments preview in place - nothing here opens a new tab, staged
 * files included.
 */
describe('AIExtractDialog staged-file preview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function stage(files: File[]) {
    const input = screen.getByTestId('ai-extract-file-input') as HTMLInputElement;
    Object.defineProperty(input, 'files', { value: files, writable: true });
    fireEvent.change(input);
  }

  it('opens the shared modal in place instead of navigating to a new tab', () => {
    const { container } = renderDialog(vi.fn());
    stage([makeFile('do.png')]);

    expect(container.querySelectorAll('a[target="_blank"]')).toHaveLength(0);
    expect(screen.queryByTestId('preview-modal')).toBeNull();

    fireEvent.click(screen.getByLabelText('Preview do.png'));

    expect(screen.getByTestId('preview-modal')).toBeInTheDocument();
    expect(screen.getByTestId('preview-modal').textContent).toContain('do.png');
  });

  it('hands the modal every staged file, starting at the one clicked', () => {
    renderDialog(vi.fn());
    stage([makeFile('first.png'), makeFile('second.jpg', 'image/jpeg')]);

    fireEvent.click(screen.getByLabelText('Preview second.jpg'));

    expect(screen.getByTestId('preview-start-index').textContent).toBe('1');
    const props = previewPropsSpy.mock.calls.at(-1)?.[0];
    expect(props.items.map((i: { name: string }) => i.name)).toEqual([
      'first.png',
      'second.jpg',
    ]);
    // Local bytes the browser already holds - no upload, so no download route.
    expect(props.items[0].url).toMatch(/^blob:/);
    expect(props.items[0].downloadUrl).toBeUndefined();
  });
});
