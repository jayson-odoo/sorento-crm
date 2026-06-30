/**
 * Export purchase request / sponsorship form to Excel in the document formats.
 * Uses xlsx (see lib/excel-utils.ts).
 */

import type { PurchaseRequest } from '../types/purchaseRequest.types';

let XLSX: typeof import('xlsx') | null = null;

async function getXLSX() {
  if (typeof window === 'undefined') {
    throw new Error('Excel export can only be used in the browser');
  }
  if (!XLSX) {
    XLSX = await import('xlsx');
  }
  return XLSX;
}

function formatDateCell(value: string | null | undefined): string {
  if (value == null || value === '') return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const day = d.getDate();
  const month = d.getMonth() + 1;
  const year = d.getFullYear();
  return `${day}/${month}/${year}`;
}

function formatDateShort(value: string | null | undefined): string {
  if (value == null || value === '') return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const day = d.getDate();
  const month = d.getMonth() + 1;
  const year = String(d.getFullYear()).slice(-2);
  return `${day}/${month}/${year}`;
}

function formatDateForSponsorship(value: string | null | undefined): string {
  if (value == null || value === '') return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${d.getDate()}-${months[d.getMonth()]}-${d.getFullYear()}`;
}

function str(value: unknown): string {
  if (value == null) return '';
  return String(value);
}

/**
 * Export a purchase request to Excel in the Purchase Request form format:
 * Purchase request number, Date, Customer, Project, Purpose, Expected dates,
 * line items table (#, Item Code, Qty, Remark), Requested by, Approved by.
 */
export async function exportPurchaseRequestToExcel(request: PurchaseRequest): Promise<void> {
  const xlsx = await getXLSX();
  const lines = request.lines ?? [];
  // Top "Date" = submitted date (auto); footer "Requested by" date = request date.
  const requestDate = formatDateShort(request.submitted_at);
  const expectedDelivery = str(request.expected_delivery_date)
    ? formatDateCell(request.expected_delivery_date)
    : str(request.expected_delivery_date);
  const expectedPO = request.expected_po_date_text ?? (request.expected_po_date ? formatDateCell(request.expected_po_date) : '');
  const requestedAt = formatDateCell(request.request_date);
  const approvedAt = request.approved_at
    ? formatDateCell(request.approved_at)
    : '';

  const aoa: (string | number)[][] = [
    ['Purchase Request'],
    ['Purchase request number:', str(request.request_number), 'Date:', requestDate],
    [],
    ['Customer Name:', str(request.customer_name)],
    ['Project Title:', str(request.project_title)],
    ['Purpose:', str(request.purpose)],
    ['Expected Date of Delivery:', expectedDelivery, 'Expected date to receive PO:', expectedPO],
    [],
    ['#', 'Item Code', 'Qty', 'Remark'],
  ];

  for (let i = 0; i < 20; i++) {
    const line = lines[i];
    aoa.push([
      i + 1,
      line ? str(line.item_code) : '',
      line != null && line.quantity != null ? Number(line.quantity) : '',
      line ? str(line.remark) : '',
    ]);
  }

  aoa.push(
    [],
    ['Requested by:', str(request.requested_by), 'Date:', requestedAt],
    ['Approved by:', str(request.approved_by), 'Date:', approvedAt],
  );

  const ws = xlsx.utils.aoa_to_sheet(aoa);
  const colWidths = [{ wch: 22 }, { wch: 24 }, { wch: 12 }, { wch: 40 }];
  ws['!cols'] = colWidths;
  const wb = xlsx.utils.book_new();
  xlsx.utils.book_append_sheet(wb, ws, 'Purchase Request');
  const filename = `Purchase_Request_${str(request.request_number) || request.id}.xlsx`;
  xlsx.writeFile(wb, filename);
}

const SORENTO_HEADER = [
  'SORENTO SDN BHD',
  'No 5, Jalan Astana 2/KU2, Bandar Bukit Raja, 41050 Klang, Selangor, Malaysia.',
  'Tel: +603-3082 9778, Fax: +603-30829278.',
];

/**
 * Export a sponsorship form to Excel in the Project Sales Sponsorship Form format:
 * Company header, Sponsorship form number, Date, Customer, Delivery Address, Project Title,
 * Total Project Value, Sponsor Subject, Date of Delivery, line items (NO., Item Code, Qty, U/P, Total), Grand Total, Requested/Approved by.
 */
export async function exportSponsorshipFormToExcel(request: PurchaseRequest): Promise<void> {
  const xlsx = await getXLSX();
  const lines = request.lines ?? [];
  // Top "Date" = submitted date (auto); footer "Requested by" date = request date.
  const requestDate = formatDateForSponsorship(request.submitted_at);
  const deliveryDate = formatDateForSponsorship(request.expected_delivery_date);
  const requestedAt = formatDateForSponsorship(request.request_date);
  const approvedAt = request.approved_at
    ? formatDateForSponsorship(request.approved_at)
    : '';
  const tpv =
    str(request.total_project_value_text) ||
    (request.total_project_value != null ? str(request.total_project_value) : '');

  const aoa: (string | number)[][] = [
    [SORENTO_HEADER[0]],
    [SORENTO_HEADER[1]],
    [SORENTO_HEADER[2]],
    [],
    ['Project Sales Sponsorship Form'],
    [],
    ['Sponsorship form number:', str(request.request_number), 'Date:', requestDate],
    [],
    ['Customer Name:', str(request.customer_name)],
    ['Delivery Address:', str(request.delivery_address)],
    ['Project Title:', str(request.project_title)],
    ['Total Project Value:', tpv],
    ['Sponsor Subject:', str(request.sponsor_subject)],
    ['Date of Delivery:', deliveryDate],
    [],
    ['NO.', 'Item Code', 'Qty', 'U/P', 'Total'],
  ];

  let grandTotal = 0;
  for (let i = 0; i < 13; i++) {
    const line = lines[i];
    const qty = line != null && line.quantity != null ? Number(line.quantity) : 0;
    const unitPrice = line != null && line.unit_price != null ? Number(line.unit_price) : 0;
    const lineTotal =
      line != null && line.total != null
        ? Number(line.total)
        : qty * unitPrice;
    grandTotal += lineTotal;
    aoa.push([
      i + 1,
      line ? str(line.item_code) : '',
      line != null && line.quantity != null ? Number(line.quantity) : '',
      unitPrice,
      lineTotal.toFixed(2),
    ]);
  }

  aoa.push(
    ['', '', '', 'Grand Total:', grandTotal.toFixed(2)],
    [],
    ['Requested by:', str(request.requested_by), 'Date:', requestedAt],
    ['Approved by:', str(request.approved_by), 'Date:', approvedAt],
  );

  const ws = xlsx.utils.aoa_to_sheet(aoa);
  const colWidths = [{ wch: 14 }, { wch: 20 }, { wch: 8 }, { wch: 10 }, { wch: 12 }];
  ws['!cols'] = colWidths;
  const wb = xlsx.utils.book_new();
  xlsx.utils.book_append_sheet(wb, ws, 'Sponsorship Form');
  const filename = `Sponsorship_Form_${str(request.request_number) || request.id}.xlsx`;
  xlsx.writeFile(wb, filename);
}

/**
 * Export based on request_type: purchase_request -> Purchase Request format, sponsorship_form -> Sponsorship Form format.
 */
export async function exportPurchaseRequestOrSponsorshipToExcel(request: PurchaseRequest): Promise<void> {
  if (request.request_type === 'sponsorship_form') {
    await exportSponsorshipFormToExcel(request);
  } else {
    await exportPurchaseRequestToExcel(request);
  }
}
