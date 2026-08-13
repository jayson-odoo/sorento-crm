/**
 * Export stock inquiry to Excel in the PRODUCT INQUIRY FORM layout.
 * Uses ExcelJS for borders, alignment, and bold (label column).
 */

import ExcelJS from 'exceljs';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';
import {
  hasRevisionLineage,
  revisionDocumentNumber,
  revisionExportFilename,
  revisionInfoRows,
  revisionSheetName,
  revisionsNewestFirst,
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
  const rows = buildFormRows(revisionEntryToStockInquiry(entry, live));
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
 * The current form, then the whole lineage newest first, one sheet each (round
 * 6, 6.4).
 *
 * Sheet 1 is byte-for-byte the export this page has always produced, so turning
 * the option on adds history and changes nothing about what was already there.
 * A submission with no lineage yet is silently just that sheet, mirroring the
 * PDF's `has_revision_history`.
 */
export async function exportStockInquiryWithRevisionsToExcel(
  inquiry: StockInquiryDetail,
  entries: FormRevisionEntry[] | null | undefined,
  filename?: string,
): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  const taken = new Set<string>();
  const currentSheetName = 'Stock Inquiry';
  taken.add(currentSheetName);
  const worksheet = workbook.addWorksheet(currentSheetName, {
    views: [{ state: 'frozen', ySplit: 1 }],
  });
  writeRowsToSheet(worksheet, buildFormRows(inquiry));

  if (hasRevisionLineage(entries)) {
    for (const entry of revisionsNewestFirst(entries)) {
      const sheet = workbook.addWorksheet(revisionSheetName(entry, taken));
      writeRowsToSheet(sheet, buildStockInquiryRevisionRows(entry, inquiry));
    }
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
