/**
 * Export stock inquiry to Excel in the STOCK INQUIRY FORM layout.
 * Uses ExcelJS for borders, alignment, and bold (label column).
 */

import ExcelJS from 'exceljs';
import { formatDate } from '@/lib/helpers';
import type { StockInquiryDetail, StockInquiry } from '../types/stockInquiry.types';

function formatDateForExport(value: Date | string | null | undefined): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  try {
    return formatDate(value);
  } catch {
    return String(value);
  }
}

/**
 * Build the form-style rows for a single stock inquiry (label in col A, value in col B).
 */
function buildFormRows(inquiry: StockInquiryDetail | StockInquiry): (string | number)[][] {
  const dateStr = inquiry.created_at
    ? formatDateForExport(inquiry.created_at)
    : '';
  const rows: (string | number)[][] = [
    ['STOCK INQUIRY FORM'],
    [],
    ['DATE:', dateStr],
    ['SALES PERSON:', inquiry.salesperson ?? ''],
    ['PRODUCT CODE:', inquiry.product_code ?? ''],
    ['ITEM DESCRIPTION:', inquiry.item_description ?? ''],
    ['PROJECT CUSTOMER:', inquiry.project_customer ?? ''],
    ['PROJECT NAME:', inquiry.project_name ?? ''],
    ['QTY:', inquiry.quantity ?? ''],
    ['DELIVERY DATE:', inquiry.delivery_date ?? ''],
    ['REMARK:', inquiry.remark ?? ''],
    [],
    [],
    ['REQUEST:'],
    ['', 'E.T.A', 'MOQ', 'PRICE', 'LEAD TIME', 'NEW ITEM'],
    [],
  ];

  rows.push(['ADDITIONAL REMARK:']);
  const additionalLines = (inquiry.additional_remark ?? '').split('\n');
  if (additionalLines.length > 0) {
    additionalLines.forEach((line) => rows.push(['', line]));
  }
  rows.push([]);

  rows.push(['COMMENT / REPLY BY PURCHASING:']);
  const responseLines = (inquiry.purchasing_response ?? '').split('\n');
  if (responseLines.length > 0) {
    responseLines.forEach((line) => rows.push(['', line]));
  }

  return rows;
}

/** Thin black border for all cells */
const thinBlackBorder = {
  top: { style: 'thin' as const },
  left: { style: 'thin' as const },
  bottom: { style: 'thin' as const },
  right: { style: 'thin' as const },
};

/** Row index (1-based) of the REQUEST sub-headings row (E.T.A, MOQ, ...) */
const REQUEST_HEADER_ROW = 16;

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
      const isRequestHeaderRow = excelRow === REQUEST_HEADER_ROW;

      if (isColA) {
        cell.font = { bold: true };
        cell.alignment = { horizontal: 'left', vertical: 'middle', wrapText: true };
      } else if (isRequestHeaderRow) {
        cell.alignment = { horizontal: 'center', vertical: 'middle', wrapText: true };
      } else {
        cell.alignment = { horizontal: 'left', vertical: 'middle', wrapText: true };
      }
    }
  }
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

  const rows = buildFormRows(inquiry);

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
  worksheet.getColumn(3).width = 12;
  worksheet.getColumn(4).width = 12;
  worksheet.getColumn(5).width = 12;
  worksheet.getColumn(6).width = 12;

  const safeName =
    inquiry.product_code?.replace(/[/\\?*\[\]:]/g, '_').slice(0, 20) ||
    'inquiry';
  const baseName = filename ?? `Stock_Inquiry_${safeName}_${formatDateForExport(inquiry.created_at ?? new Date()).replace(/\//g, '-')}`;
  const finalFilename = baseName.endsWith('.xlsx') ? baseName : `${baseName}.xlsx`;

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = finalFilename;
  a.click();
  URL.revokeObjectURL(url);
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
    worksheet.getColumn(3).width = 12;
    worksheet.getColumn(4).width = 12;
    worksheet.getColumn(5).width = 12;
    worksheet.getColumn(6).width = 12;
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
