import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { TemplateUploadDialog, type ValidateImportResult } from './TemplateUploadDialog';

vi.mock('@/lib/excel-utils', () => ({
  parseExcelFile: vi.fn(async () => [{ 'Item Code': 'P1', 'Item Group': 'SRT-FT' }]),
}));

vi.mock('@/hooks/use-excel-accept', () => ({
  useExcelAccept: () => '.xlsx,.xls',
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

async function runTest(result: ValidateImportResult) {
  render(
    <TemplateUploadDialog
      open
      onOpenChange={vi.fn()}
      onUpload={vi.fn()}
      onTest={vi.fn(async () => result)}
      accept=".xlsx,.xls"
    />,
  );
  // The file picker lives inside the shared FileDropzone, reached by the accessible
  // name the dialog gives it. Nothing else about the zone is asserted here - that is
  // FileDropzone's own suite - only that a picked file reaches the Test handler.
  const input = screen.getByLabelText('Excel file') as HTMLInputElement;
  // The dropzone filters on the extension, so the name has to be a real .xlsx.
  const file = new File(['x'], 'items.xlsx', { type: 'application/vnd.ms-excel' });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: /test/i }));
}

describe('TemplateUploadDialog validation preview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows warnings on a VALID file (auto-created master data must not be hidden)', async () => {
    await runTest({
      valid: true,
      errors: [],
      warnings: ['87 new categories will be created: ACC-ALAN, ACC-AT'],
      summary: { total_rows: 10962, would_create: 10962, new_categories: 87, new_brands: 12, new_uoms: 0 },
    });

    await waitFor(() => expect(screen.getByText('No errors')).toBeInTheDocument());
    expect(screen.getByText('Warnings (1)')).toBeInTheDocument();
    expect(
      screen.getByText('87 new categories will be created: ACC-ALAN, ACC-AT'),
    ).toBeInTheDocument();
  });

  it('summarises the master data the import will create', async () => {
    await runTest({
      valid: true,
      errors: [],
      warnings: [],
      summary: { total_rows: 3, would_create: 3, would_update: 0, error_count: 0, new_categories: 2, new_brands: 1, new_uoms: 4 },
    });

    await waitFor(() => expect(screen.getByText('Validation result')).toBeInTheDocument());
    const summary = screen.getByText(/Rows: 3/);
    expect(summary.textContent).toContain('New categories: 2');
    expect(summary.textContent).toContain('New brands: 1');
    expect(summary.textContent).toContain('New UOMs: 4');
  });

  it('still shows errors when the file is invalid', async () => {
    await runTest({
      valid: false,
      errors: ["Row 1 (P1): item_group is required"],
      warnings: ['1 new brands will be created: SORENTO'],
      summary: { total_rows: 1, error_count: 1 },
    });

    await waitFor(() => expect(screen.getByText('Errors (1)')).toBeInTheDocument());
    expect(screen.getByText('Warnings (1)')).toBeInTheDocument();
    expect(screen.queryByText('No errors')).toBeNull();
  });
});
