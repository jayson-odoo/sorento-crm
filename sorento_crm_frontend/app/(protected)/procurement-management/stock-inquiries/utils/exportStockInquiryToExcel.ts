/**
 * Export stock inquiry to Excel in the STOCK INQUIRY FORM layout.
 * Uses ExcelJS for borders, alignment, and bold (label column + selected brand).
 */

import ExcelJS from 'exceljs';
import { formatDate } from '@/lib/helpers';
import type { StockInquiryDetail, StockInquiry } from '../types/stockInquiry.types';

const CUSTOMER_BUDGET_BRANDS = ['SORENTO', 'MOCHA', 'CABANA', 'NO LOGO'] as const;

/** Return 0-based column index (B=0, C=1, D=2, E=3) for the chosen brand, or -1 if no match */
function getBrandColumnIndex(brand: string | null | undefined): number {
  if (brand == null || brand === '') return -1;
  const normalized = String(brand).toUpperCase().trim();
  const idx = CUSTOMER_BUDGET_BRANDS.indexOf(normalized as (typeof CUSTOMER_BUDGET_BRANDS)[number]);
  return idx >= 0 ? idx : -1;
}

/** Selected brand cell gets "★ BRAND", others stay as-is; chosen one will be bolded via style */
function buildBrandsRow(brand: string | null | undefined): (string | number)[] {
  const colIndex = getBrandColumnIndex(brand);
  return [
    '',
    ...CUSTOMER_BUDGET_BRANDS.map((name, i) => (i === colIndex ? `★ ${name}` : name)),
  ];
}

function formatDateForExport(value: Date | string | null | undefined): string {
  if (value == null) return '';
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
  const deliveryStr = inquiry.delivery_date
    ? formatDateForExport(inquiry.delivery_date)
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
    ['DELIVERY DATE:', deliveryStr],
    [],
    ['REMARK:'],
  ];
  rows.push([]);
  rows.push([]);
  rows.push([]);
  rows.push([]);

  rows.push(['CUSTOMER BUDGET PRICE:']);
  rows.push(buildBrandsRow(inquiry.brand));
  rows.push([]);

  rows.push(['REQUEST:']);
  rows.push(['', 'E.T.A', 'MOQ', 'PRICE', 'LEAD TIME', 'NEW ITEM']);
  rows.push([]);

  rows.push(['COMPETITOR BRAND:', '']);
  rows.push([]);

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

/** Row index (1-based) of the CUSTOMER BUDGET PRICE brands row */
const BRANDS_ROW = 18;
/** Row index (1-based) of the REQUEST sub-headings row (E.T.A, MOQ, ...) */
const REQUEST_HEADER_ROW = 21;

function applyStylesToSheet(
  worksheet: ExcelJS.Worksheet,
  rows: (string | number)[][],
  brand: string | null | undefined,
): void {
  const brandColIndex = getBrandColumnIndex(brand);

  for (let r = 0; r < rows.length; r++) {
    const row = rows[r];
    const excelRow = r + 1;
    for (let c = 0; c < (row?.length ?? 0); c++) {
      const cell = worksheet.getCell(excelRow, c + 1);
      const value = row[c];
      cell.value = value !== '' && value !== null && value !== undefined ? value : '';
      cell.border = thinBlackBorder;

      const isColA = c === 0;
      const isBrandRow = excelRow === BRANDS_ROW;
      const isRequestHeaderRow = excelRow === REQUEST_HEADER_ROW;
      const isBrandCellInBrandRow = isBrandRow && c >= 1 && c <= 4;
      const isChosenBrandCell = isBrandRow && c >= 1 && c - 1 === brandColIndex;

      if (isColA) {
        // Left column labels: bold, left-aligned, vertical center
        cell.font = { bold: true };
        cell.alignment = { horizontal: 'left', vertical: 'middle', wrapText: true };
      } else if (isBrandCellInBrandRow || isRequestHeaderRow) {
        // Brand names and request sub-headings: horizontal center
        cell.alignment = { horizontal: 'center', vertical: 'middle', wrapText: true };
        if (isChosenBrandCell) {
          cell.font = { bold: true };
        }
      } else {
        // Other value cells: left-aligned
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

  applyStylesToSheet(worksheet, rows, inquiry.brand);

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

    applyStylesToSheet(worksheet, rows, inquiry.brand);

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
