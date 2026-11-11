import type { QueryClient } from '@tanstack/react-query';
import type { ResumePoLinkInput } from './poLinkService';
import type {
  PoLinkOptions,
  PoLinkResult,
  SnapshotPoLink,
} from '../../stock-debt/types/stockDebtSnapshot.types';

/** One sales order line in the PO link popup, whichever screen it came from. */
export interface PoLinkLine {
  sales_order_line_id: string;
  so_number: string;
  line_no?: number | null;
  open_qty: number;
  warehouse_code?: string | null;
  required_date?: string | null;
  /** What AutoCount says now: outstanding and the POs already linked. */
  now?: { so_status?: string | null; open_qty: number; po_links?: SnapshotPoLink[] };
}

export type PoLinkAnswer = { results: PoLinkResult[] };

/** Where a screen's PO link calls go. Stock Debt and Order Inquiries each build one. */
export interface PoLinkTarget {
  /** Query key of the screen's options read. */
  key: readonly unknown[];
  api: {
    options: () => Promise<PoLinkOptions>;
    link: (lines: Array<{ sales_order_line_id: string; po_line_id: string; qty: number }>) => Promise<PoLinkAnswer>;
    unlink: (poLineIds: string[]) => Promise<PoLinkAnswer>;
    change: (changes: Array<{ sales_order_line_id: string; po_line_id: string }>) => Promise<PoLinkAnswer>;
    relocate: (poLineId: string) => Promise<PoLinkResult>;
    resume: (input: ResumePoLinkInput) => Promise<PoLinkResult>;
    relink?: (moves: Array<{ po_line_id: string; to_sales_order_line_id: string }>) => Promise<PoLinkAnswer>;
  };
  /** Read the screen's own data again after any write. */
  refresh?: (queryClient: QueryClient) => void;
}

/** An Order Inquiry row left out of the popup, with the plain reason. */
export interface PoLinkSkippedRow {
  inquiry_no: string | null;
  item_code: string | null;
  reason: string;
}

/** Options of ticked Order Inquiry rows: Stock Debt's shape plus the lines and the left-out rows. */
export type OiPoLinkOptions = PoLinkOptions & { lines: PoLinkLine[]; skipped: PoLinkSkippedRow[] };
