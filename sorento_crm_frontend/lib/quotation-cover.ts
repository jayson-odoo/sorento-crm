/**
 * The quotation cover page as the sign link, the quotation's Cover letter tab and the designer
 * preview all read it (backend `quotation_cover_service.cover_payload`).
 */

/** One cover row. The terms row carries `html`, every other row `text`. */
export interface CoverRow {
  key: string;
  label: string;
  text?: string | null;
  html?: string | null;
}

export interface CoverPageData {
  sender_name: string | null;
  sender_logo_url: string | null;
  cover_rows: CoverRow[];
  /** Set for a designed cover (layout 3); absent for the fixed #2088 cover. */
  cover_title?: string | null;
  cover_show_letterhead?: boolean | null;
  cover_intro_html?: string | null;
  cover_closing_html?: string | null;
}

export interface CoverDesignRow {
  key: string;
  shown: boolean;
  label: string;
}

/** `quotation_templates.design` of a cover_page template. */
export interface CoverDesign {
  show_letterhead: boolean;
  title: string;
  rows: CoverDesignRow[];
  closing_html: string;
}

export const COVER_MAX_LABEL = 60;
