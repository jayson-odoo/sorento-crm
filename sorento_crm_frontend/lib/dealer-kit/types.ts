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

/** How a bound background asset is laid out behind its section. */
export type SectionBackgroundFit = 'width' | 'cover';

export interface SectionStyle {
  background?: string;
  paddingY?: 'none' | 'sm' | 'md' | 'lg' | 'xl';
  /**
   * The artwork behind this section, as an asset ID and never a URL.
   *
   * An ID because the file gets renamed, re-signed and (one day) migrated
   * between storage providers, and none of those may break a page that has
   * already been published. The reader's URL is resolved at request time and
   * arrives alongside the document in `assets`.
   */
  backgroundAssetId?: string;
  /**
   * A flyer's header band is roughly 4:1 and belongs across the top at its own
   * proportions; artwork that WAS the whole printed page fills the section.
   * Sections are as tall as their content, so telling a band to cover magnifies
   * it until only a smear shows.
   */
  backgroundFit?: SectionBackgroundFit;
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
  /**
   * The promotion this brochure quotes, when one does. Null is a finished
   * state: the catalogue shows list prices.
   */
  promotionId: string | null;
  /**
   * That promotion's name, resolved by the backend so no id is ever rendered.
   * Null when nothing is linked, and also when the promotion carries no
   * description - the UI supplies the words for that case.
   */
  promotionLabel: string | null;
}

export interface Page extends PageSummary {
  /**
   * The tile design every collection block on this page inherits.
   *
   * On the PAGE because "how do the tiles look" is one editorial decision about
   * the document. A block may still name its own, which wins. Null falls back
   * to the renderer's built-in field list, which is a state it has.
   */
  tileTemplateId: string | null;
  /** Its name, resolved server-side. No uuid reaches the screen. */
  tileTemplateName: string | null;
  doc: PageDoc;
  versions: PageVersion[];
  /**
   * assetId -> signed URL for the section backgrounds this document binds.
   *
   * The same map the public catalogue and the print payload carry, and resolved
   * by the same server-side call, so the builder paints what the reader gets.
   * An asset that could not be signed is ABSENT rather than a URL the CDN
   * answers 403 to: the section has a designed state for "no picture" and none
   * for a broken one.
   */
  assets: Record<string, string>;
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
  | 'offerPrice'
  | 'dimensions'
  | 'badges'
  | 'cta';

/**
 * A collection's resolved membership, as the renderer receives it.
 *
 * Resolution happens SERVER-side per viewer (AC-G2): the saved document holds
 * only a `collectionId`, and what comes back here already reflects who is
 * looking. `price` is a formatted string rather than a number because the
 * server decides both the figure and whether the viewer may see one at all -
 * `null` means "not for this reader", and there is no number in the payload to
 * leak (AC-G7).
 */
export interface ResolvedTile {
  productId: string;
  productCode: string;
  productName: string;
  /** The LIST price: the original, higher figure a flyer prints as "LP". */
  price: string | null;
  /**
   * The PROMOTIONAL price: what this reader actually pays, when an offer
   * reaches them. Sent BESIDE `price` rather than instead of it, so the tile
   * can strike the list price through and show what is being saved. `null`
   * means no offer applies to this reader - which is also how an offer they
   * may not see arrives: with no figure to recover (ADR 0008 rule 2).
   */
  offerPrice: string | null;
  invoicePrice: string | null;
  imageUrl: string | null;
  dimensions: string | null;
  badges: string[];
}

export interface ResolvedCollection {
  collectionId: string;
  name: string | null;
  tiles: ResolvedTile[];
}

export interface CollectionSummary {
  id: string;
  /** Page-scoped collections are unnamed until someone saves them to the library. */
  name: string | null;
  scope: 'page' | 'library';
  memberCount: number;
  updatedAt: string;
}

export interface BundleComponentView {
  productId: string;
  productCode: string;
  productName: string;
  quantity: number;
  /** The bundle price allocated to this line. Sums exactly to the bundle price. */
  allocated: string;
  available: boolean;
}

/**
 * A bundle as rendered: ONE priced heading with its components beneath (AC-F12).
 * `available` is derived at read time from the components and is never stored
 * (AC-F10) - a bundle with a discontinued part can never render as orderable.
 */
export interface ResolvedBundle {
  id: string;
  name: string;
  price: string;
  available: boolean;
  unavailableReason: string | null;
  components: BundleComponentView[];
}

export interface BundleSummary {
  id: string;
  name: string;
  price: string;
  componentCount: number;
  available: boolean;
}

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
