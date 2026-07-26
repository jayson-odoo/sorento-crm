/**
 * Dealer Kit page document model.
 *
 * `PageDoc` is exactly what gets stored in `dealer_kit.page_version.doc`.
 *
 * The hard rule (AC-G1): a document stores BINDINGS, never resolved values. No
 * price, no access decision, no product snapshot ever appears in here. A price
 * string found in a saved doc is a defect, not a shortcut - it is what makes one
 * published page serve staff, dealers and consumers with the price each is
 * allowed to see.
 */

import type { BlockLayout, PageLayouts } from './deriveLayout';

export type { BlockLayout, PageLayouts };

export type BlockType =
  | 'text'
  | 'heading'
  | 'image'
  | 'asset'
  | 'artboard'
  | 'collection'
  | 'bundle'
  | 'spacer';

/** Per-section print behaviour (AC-H1). */
export type SectionPrintMode = 'include' | 'exclude' | 'breakBefore';

export interface TextBlockProps {
  text: string;
  align?: 'left' | 'center' | 'right';
  /** Display scale, resolved to real type sizes by the renderer. */
  scale?: 'sm' | 'base' | 'lg' | 'xl' | '2xl';
}

export interface ImageBlockProps {
  /** Asset id. Never a filename or URL - renaming a file must not break a page (AC-D3). */
  assetId: string | null;
  alt?: string;
  fit?: 'cover' | 'contain';
}

export interface CollectionBlockProps {
  collectionId: string | null;
  tileTemplateId: string | null;
  /**
   * Tile density per breakpoint. This is why layout derivation can stack blocks
   * full-width without making product grids absurd - density is the block's own
   * business, not the grid's.
   */
  columns: { desktop: number; tablet: number; mobile: number };
}

export interface BundleBlockProps {
  bundleId: string | null;
  tileTemplateId: string | null;
}

export interface ArtboardBlockProps {
  /** Fixed aspect ratio, e.g. 16 / 9. The one place free positioning is allowed (AC-C10). */
  aspectRatio: number;
  children: ArtboardChild[];
}

export interface ArtboardChild {
  id: string;
  kind: 'text' | 'asset';
  /** Percentages of the artboard box, so the artboard scales cleanly. */
  xPct: number;
  yPct: number;
  widthPct: number;
  text?: string;
  assetId?: string;
}

export type BlockProps =
  | ({ kind: 'text' } & TextBlockProps)
  | ({ kind: 'heading' } & TextBlockProps)
  | ({ kind: 'image' } & ImageBlockProps)
  | ({ kind: 'asset' } & ImageBlockProps)
  | ({ kind: 'artboard' } & ArtboardBlockProps)
  | ({ kind: 'collection' } & CollectionBlockProps)
  | ({ kind: 'bundle' } & BundleBlockProps)
  | { kind: 'spacer' };

export interface Block {
  id: string;
  type: BlockType;
  props: BlockProps;
  /**
   * Hidden when the page is printed. Defaults true for interactive block types
   * (buttons, filters, add-to-selection) and false for content (AC-H2).
   */
  hideInPrint?: boolean;
}

export interface SectionStyle {
  background?: string;
  paddingY?: 'none' | 'sm' | 'md' | 'lg' | 'xl';
}

export interface Section {
  id: string;
  name: string;
  style: SectionStyle;
  blocks: Block[];
  /** Placement per breakpoint, keyed by block id. */
  layouts: PageLayouts;
  printMode: SectionPrintMode;
}

export type PaperSize = 'A4' | 'A3' | 'Letter';
export type PaperOrientation = 'portrait' | 'landscape';

export interface PrintProfile {
  pageSize: PaperSize;
  orientation: PaperOrientation;
  margins: { top: number; right: number; bottom: number; left: number };
  cover: boolean;
  headerFooter: { left: string; right: string; pageNumbers: boolean };
}

export interface PageDoc {
  sections: Section[];
  printProfile: PrintProfile;
}

/** Publishing labels. Moving one is what goes live - versions are never edited (AC-B3). */
export type PageLabel = 'published' | 'staging';

export interface PageVersion {
  id: string;
  version: number;
  commitMessage: string | null;
  createdBy: string;
  createdAt: string;
  labels: PageLabel[];
}

export interface PageSummary {
  id: string;
  name: string;
  slug: string;
  /**
   * The shareable address, resolved by the backend as `/c/{companyCode}/{slug}`.
   * Built server-side because the company segment is what keeps two companies'
   * identical slugs apart, and the UI holds no company id to derive it from.
   */
  publicPath: string | null;
  updatedAt: string;
  publishedVersion: number | null;
  latestVersion: number;
}

export interface Page extends PageSummary {
  doc: PageDoc;
  versions: PageVersion[];
}

export type AssetKind = 'logo' | 'icon' | 'badge' | 'decorative';

export interface Asset {
  id: string;
  name: string;
  kind: AssetKind;
  tags: string[];
  url: string;
  /** Rendered at print DPI when vector, so SVG stays crisp in the PDF (AC-D5). */
  isVector: boolean;
}

export interface TileTemplate {
  id: string;
  name: string;
  /** Which product fields the tile binds. Never resolved values. */
  fields: TileField[];
  updatedAt: string;
}

export type TileField =
  | 'image'
  | 'name'
  | 'code'
  | 'price'
  | 'dimensions'
  | 'badges'
  | 'cta';

export const PAPER_SIZES_MM: Record<PaperSize, { width: number; height: number }> = {
  A4: { width: 210, height: 297 },
  A3: { width: 297, height: 420 },
  Letter: { width: 215.9, height: 279.4 },
};

export const DEFAULT_PRINT_PROFILE: PrintProfile = {
  pageSize: 'A4',
  orientation: 'portrait',
  margins: { top: 15, right: 15, bottom: 15, left: 15 },
  cover: true,
  headerFooter: { left: '', right: '', pageNumbers: true },
};

/** Block types that are interactive, so they drop out of print by default (AC-H2). */
const INTERACTIVE_BLOCK_TYPES: ReadonlySet<BlockType> = new Set<BlockType>([]);

export function defaultHideInPrint(type: BlockType): boolean {
  return INTERACTIVE_BLOCK_TYPES.has(type);
}
