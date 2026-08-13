/**
 * The AutoCount reorder-level upload (S13c).
 *
 * The rule worth pinning: a level the buyer set by hand is never silently overwritten -
 * the disagreement is put on screen as "kept yours", named per item.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ReorderLevelUploadDialog } from './ReorderLevelUploadDialog';
import type { LevelImportOutcome } from '../services/reorderLevelImportService';

Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const previewLevelImport = vi.fn();
const applyLevelImport = vi.fn();
vi.mock('../services/reorderLevelImportService', () => ({
  previewLevelImport: (f: File) => previewLevelImport(f),
  applyLevelImport: (f: File) => applyLevelImport(f),
}));
vi.mock('../services/outstandingImportService', async (orig) => ({
  ...(await orig()),
  getOutstandingUploadConfig: () => Promise.resolve({ allowed_extensions: ['.xlsx'] }),
}));

const outcome = (over: Partial<LevelImportOutcome> = {}): LevelImportOutcome => ({
  readable: true,
  missing_columns: [],
  unmapped_headers: [],
  problems: [],
  total_rows: 2,
  created: 1,
  updated: 1,
  unchanged: 0,
  conflicts: 0,
  conflict_rows: [],
  sample: [],
  ok: true,
  ...over,
});

function pickFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(['x'], 'levels.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  fireEvent.change(input, { target: { files: [file] } });
}

beforeEach(() => {
  previewLevelImport.mockReset();
  applyLevelImport.mockReset();
});

describe('ReorderLevelUploadDialog', () => {
  it('previews the file and shows what it would do before anything is written', async () => {
    previewLevelImport.mockResolvedValue(outcome());
    render(<ReorderLevelUploadDialog open onOpenChange={() => {}} />);

    pickFile();

    await waitFor(() => expect(screen.getByText('New levels')).toBeInTheDocument());
    expect(applyLevelImport).not.toHaveBeenCalled();
  });

  it('names the hand-set levels it will keep, per item', async () => {
    previewLevelImport.mockResolvedValue(
      outcome({
        conflicts: 1,
        conflict_rows: [
          { item_code: 'MWC7624', location: 'BRW', held_level: 200, file_level: 120, held_source: 'manual' },
        ],
      }),
    );
    render(<ReorderLevelUploadDialog open onOpenChange={() => {}} />);

    pickFile();

    await waitFor(() => expect(screen.getByText(/will be kept/)).toBeInTheDocument());
    expect(screen.getByText(/MWC7624 at BRW: yours 200, file 120/)).toBeInTheDocument();
  });

  it('refuses to confirm an unreadable file and says which column is missing', async () => {
    previewLevelImport.mockResolvedValue(
      outcome({ readable: false, ok: false, missing_columns: ['reorder_level'] }),
    );
    render(<ReorderLevelUploadDialog open onOpenChange={() => {}} />);

    pickFile();

    await waitFor(() => expect(screen.getByText(/missing reorder level/i)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /confirm upload/i })).toBeDisabled();
  });

  it('applies on confirm and reports what actually happened', async () => {
    previewLevelImport.mockResolvedValue(outcome());
    applyLevelImport.mockResolvedValue(outcome({ created: 1, updated: 1 }));
    render(<ReorderLevelUploadDialog open onOpenChange={() => {}} />);

    pickFile();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirm upload/i })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: /confirm upload/i }));

    await waitFor(() => expect(applyLevelImport).toHaveBeenCalledTimes(1));
    // The flow is over: nothing left to confirm, only to close.
    expect(screen.queryByRole('button', { name: /confirm upload/i })).not.toBeInTheDocument();
  });
});
