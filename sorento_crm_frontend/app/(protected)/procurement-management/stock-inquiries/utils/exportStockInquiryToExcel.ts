/**
 * Export stock inquiry to Excel in the PRODUCT INQUIRY FORM layout.
 * Uses ExcelJS for borders, alignment, and bold (label column).
 */

import ExcelJS from 'exceljs';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';
import {
  appendedRevisionEntries,
  latestRevisionEntry,
  revisionDocumentNumber,
  revisionExportFilename,
  revisionInfoRows,
  revisionSheetName,
} from '@/lib/revision-export';
import type { StockInquiryDetail, StockInquiry } from '../types/stockInquiry.types';
import { revisionEntryToStockInquiry } from './revisionEntryToStockInquiry';

/** Date only in Malaysia timezone for Excel (no time). */
function formatDateForExport(value: Date | string | null | undefined): string {
  if (value == null) return '';
  try {
    return formatDateInMalaysia(value);
  } catch {
    return String(value);
  }
}

/**
 * Build the form-style rows for a single stock inquiry (label in col A, value in col B).
 *
 * Exported so the revision variants below (and their tests) build on THIS row
 * list rather than a second copy of the layout.
 */
export function buildFormRows(inquiry: StockInquiryDetail | StockInquiry): (string | number)[][] {
  const dateStr = inquiry.created_at
    ? formatDateForExport(inquiry.created_at)
    : '';
  const rows: (string | number)[][] = [
    ['PRODUCT INQUIRY FORM'],
    [],
    ['DATE:', dateStr],
    ['STOCK INQUIRY NUMBER:', inquiry.inquiry_number ?? ''],
    ['SALES PERSON:', inquiry.salesperson ?? ''],
    ['PRODUCT CODE:', inquiry.product_code ?? ''],
    ['ITEM DESCRIPTION:', inquiry.item_description ?? ''],
    ['PROJECT CUSTOMER:', inquiry.project_customer ?? ''],
    ['PROJECT NAME:', inquiry.project_name ?? ''],
    ['QTY:', inquiry.quantity ?? ''],
    ['DELIVERY DATE:', inquiry.delivery_date ?? ''],
    ['REMARK:', inquiry.remark ?? ''],
    [],
    ['ADDITIONAL REMARK:', inquiry.additional_remark ?? ''],
    [],
    ['COMMENT / REPLY BY PURCHASING:', inquiry.purchasing_response ?? ''],
  ];

  return rows;
}

/** Thin black border for all cells */
const thinBlackBorder = {
  top: { style: 'thin' as const },
  left: { style: 'thin' as const },
  bottom: { style: 'thin' as const },
  right: { style: 'thin' as const },
};

function applyStylesToSheet(
  worksheet: ExcelJS.Worksheet,
  rows: (string | number)[][],
): void {
  for (let r = 0; r < rows.length; r++) {
    const row = rows[r];
    const excelRow = r + 1;
    for (let c = 0; c < (row?.length ?? 0); c++) {
      const cell = worksheet.getCell(excelRow, c + 1);
      const value = row[c];
      cell.value = value !== '' && value !== null && value !== undefined ? value : '';
      cell.border = thinBlackBorder;

      const isColA = c === 0;

      if (isColA) {
        cell.font = { bold: true };
      }
      cell.alignment = { horizontal: 'left', vertical: 'middle', wrapText: true };
    }
  }
}

/** Write one row list into a sheet and style it. Shared by every export here so
 *  a revision sheet is laid out by the same code as the current form. */
function writeRowsToSheet(worksheet: ExcelJS.Worksheet, rows: (string | number)[][]): void {
  for (let r = 0; r < rows.length; r++) {
    const row = rows[r];
    const excelRow = worksheet.getRow(r + 1);
    for (let c = 0; c < (row?.length ?? 0); c++) {
      const value = row[c];
      excelRow.getCell(c + 1).value = value !== '' && value !== null && value !== undefined ? value : '';
    }
    excelRow.commit();
  }

  applyStylesToSheet(worksheet, rows);

  worksheet.getColumn(1).width = 28;
  worksheet.getColumn(2).width = 24;
}

/** The workbook's own filename, ending in `.xlsx`. */
function stockInquiryFilename(inquiry: StockInquiryDetail | StockInquiry, filename?: string): string {
  const safeName =
    inquiry.product_code?.replace(/[/\\?*\[\]:]/g, '_').slice(0, 20) ||
    'inquiry';
  const baseName = filename ?? `Stock_Inquiry_${safeName}_${formatDateForExport(inquiry.created_at ?? new Date()).replace(/\//g, '-')}`;
  return baseName.endsWith('.xlsx') ? baseName : `${baseName}.xlsx`;
}

async function downloadWorkbook(workbook: ExcelJS.Workbook, filename: string): Promise<void> {
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Export a single stock inquiry to an Excel file in the form layout.
 */
export async function exportStockInquiryToExcel(
  inquiry: StockInquiryDetail,
  filename?: string,
): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Stock Inquiry', { views: [{ state: 'frozen', ySplit: 1 }] });

  writeRowsToSheet(worksheet, buildFormRows(inquiry));

  await downloadWorkbook(workbook, stockInquiryFilename(inquiry, filename));
}

/**
 * The same form, filled in from ONE stored revision (round 6, 6.3).
 *
 * The layout is `buildFormRows` unchanged - only the values differ, and they all
 * come from the snapshot (see `revisionEntryToStockInquiry`). What is added is
 * the block that says which version the sheet is: without it a page of
 * superseded values is indistinguishable from the current form.
 */
export function buildStockInquiryRevisionRows(
  entry: FormRevisionEntry,
  live: StockInquiryDetail,
): (string | number)[][] {
  return withVersionBlock(buildFormRows(revisionEntryToStockInquiry(entry, live)), entry);
}

/**
 * The version block under the document title: which version these rows are, why
 * it changed, when it was sent.
 *
 * One inserter for both users of it - a revision sheet, and the CURRENT sheet of
 * an include-revisions workbook (whose newest entry no longer gets a sheet of its
 * own). `entry` null leaves the rows exactly as the form builder produced them.
 */
function withVersionBlock(
  rows: (string | number)[][],
  entry: FormRevisionEntry | null,
): (string | number)[][] {
  if (!entry) return rows;
  // rows[0] is the document title and rows[1] the blank beneath it; the form
  // itself starts at rows[2] and is left exactly as it is.
  return [
    rows[0] ?? [],
    [],
    ...revisionInfoRows(entry, { uppercase: true }),
    [],
    ...rows.slice(2),
  ];
}

/**
 * One superseded version as its own workbook (round 6, 6.3).
 *
 * Named after THAT version's own document number, exactly as the PDF of the
 * same revision is - not after the record's current number with a second
 * revision marker appended.
 */
export async function exportStockInquiryRevisionToExcel(
  entry: FormRevisionEntry,
  live: StockInquiryDetail,
): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Stock Inquiry', { views: [{ state: 'frozen', ySplit: 1 }] });

  writeRowsToSheet(worksheet, buildStockInquiryRevisionRows(entry, live));

  await downloadWorkbook(
    workbook,
    revisionExportFilename(
      'Stock_Inquiry',
      entry,
      revisionDocumentNumber(entry, 'inquiry_number', live.inquiry_number) ?? live.id,
    ),
  );
}

/**
 * The sheets an include-revisions workbook holds, in order (round 6, 6.4;
 * corrected round 7).
 *
 * Sheet 1 is the current form - byte-for-byte the export this page has always
 * produced, plus the version block naming the newest entry when there is one.
 * Then one sheet per EARLIER version, newest first. The newest entry gets no
 * sheet of its own: it is the version sheet 1 shows, so a sheet for it repeated
 * the same form with the office fields blanked. Same rule as the PDF's
 * `appended_revision_entries`, from the same shared helper.
 *
 * A submission with no lineage yet is silently just the current sheet.
 *
 * Split out from the writer so the sheet set is assertable without producing a
 * file - the thing that can be wrong here is WHICH sheets a workbook has.
 */
export function buildStockInquiryRevisionSheets(
  inquiry: StockInquiryDetail,
  entries: FormRevisionEntry[] | null | undefined,
): { name: string; rows: (string | number)[][] }[] {
  const currentSheetName = 'Stock Inquiry';
  const taken = new Set<string>([currentSheetName]);
  return [
    {
      name: currentSheetName,
      rows: withVersionBlock(buildFormRows(inquiry), latestRevisionEntry(entries)),
    },
    ...appendedRevisionEntries(entries).map((entry) => ({
      name: revisionSheetName(entry, taken),
      rows: buildStockInquiryRevisionRows(entry, inquiry),
    })),
  ];
}

/**
 * The current form, then every earlier version newest first, one sheet each
 * (round 6, 6.4; corrected round 7).
 */
export async function exportStockInquiryWithRevisionsToExcel(
  inquiry: StockInquiryDetail,
  entries: FormRevisionEntry[] | null | undefined,
  filename?: string,
): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  for (const sheet of buildStockInquiryRevisionSheets(inquiry, entries)) {
    writeRowsToSheet(
      workbook.addWorksheet(sheet.name, { views: [{ state: 'frozen', ySplit: 1 }] }),
      sheet.rows,
    );
  }

  await downloadWorkbook(workbook, stockInquiryFilename(inquiry, filename));
}

/**
 * Export multiple stock inquiries to one Excel file, one sheet per inquiry.
 */
export async function exportStockInquiriesToExcel(
  inquiries: StockInquiryDetail[] | StockInquiry[],
  filename: string = 'Stock_Inquiries.xlsx',
): Promise<void> {
  const workbook = new ExcelJS.Workbook();

  inquiries.forEach((inquiry, index) => {
    const rows = buildFormRows(inquiry);
    const safeProduct = inquiry.product_code?.replace(/[/\\?*\[\]:]/g, '_').slice(0, 25) ?? 'Inquiry';
    const sheetName = `${index + 1}_${safeProduct}`.slice(0, 31);
    const worksheet = workbook.addWorksheet(sheetName);

    for (let r = 0; r < rows.length; r++) {
      const row = rows[r];
      const excelRow = worksheet.getRow(r + 1);
      for (let c = 0; c < (row?.length ?? 0); c++) {
        const value = row[c];
        excelRow.getCell(c + 1).value = value !== '' && value !== null && value !== undefined ? value : '';
      }
      excelRow.commit();
    }

    applyStylesToSheet(worksheet, rows);

    worksheet.getColumn(1).width = 28;
    worksheet.getColumn(2).width = 24;
  });

  const finalFilename = filename.endsWith('.xlsx') ? filename : `${filename}.xlsx`;
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = finalFilename;
  a.click();
  URL.revokeObjectURL(url);
}
