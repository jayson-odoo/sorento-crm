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

/** One printed field of a layout 4 cover section (QUOTE-COVER-FIELDS). */
export interface CoverCell {
  source: string;
  label: string;
  text?: string | null;
  html?: string | null;
}

export type CoverSectionStyle =
  | 'fields'
  | 'title'
  | 'numbered'
  | 'signature'
  | 'footer';

/** A layout 4 section with its values: `cells` holds one list per column. */
export interface CoverSection {
  style: CoverSectionStyle;
  label: string;
  columns: number;
  cells: CoverCell[][];
}

export interface CoverPageData {
  sender_name: string | null;
  sender_logo_url: string | null;
  cover_rows: CoverRow[];
  /** Set for a layout 4 cover (sections); absent or null for layouts 1 to 3. */
  cover_sections?: CoverSection[] | null;
  /** Set for a designed cover (layout 3); absent for the fixed #2088 cover. */
  cover_title?: string | null;
  cover_show_letterhead?: boolean | null;
  cover_intro_html?: string | null;
  cover_closing_html?: string | null;
}

/** One row of a design section: a source field, its printed label, a tick and its column. */
export interface CoverDesignRow {
  source: string;
  shown: boolean;
  label: string;
  column: number;
}

export interface CoverDesignSection {
  style: CoverSectionStyle;
  label: string;
  columns: number;
  rows: CoverDesignRow[];
}

/** `quotation_templates.design` of a cover_page template (the server normalizes older designs). */
export interface CoverDesign {
  show_letterhead: boolean;
  title: string;
  sections: CoverDesignSection[];
  closing_html: string;
}

/** One field a cover row can print (`GET .../cover-sources`). */
export interface CoverSource {
  key: string;
  caption: string;
  group: string;
  default_label: string;
}

export const COVER_MAX_LABEL = 60;
export const COVER_MAX_COLUMNS = 6;
export const COVER_MAX_SECTIONS = 12;

export const COVER_SECTION_STYLES: {
  value: CoverSectionStyle;
  label: string;
}[] = [
  { value: 'fields', label: 'Label and value' },
  { value: 'title', label: 'Centred title' },
  { value: 'numbered', label: 'Numbered list' },
  { value: 'signature', label: 'Signature block' },
  { value: 'footer', label: 'Footer' },
];
