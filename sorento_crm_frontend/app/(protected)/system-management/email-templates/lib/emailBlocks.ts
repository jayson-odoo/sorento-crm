import type { EmailBlock, EmailBlockType, EmailTemplate } from '../types/emailTemplate.types';

/** Human labels for the "Add block" menu and the read-only summary rows (AC-EM040/042). */
export const BLOCK_TYPE_LABELS: Record<EmailBlockType, string> = {
  brand_header: 'Brand header',
  heading: 'Heading',
  intro: 'Intro',
  facts: 'Facts table',
  button: 'CTA button',
  link: 'Secondary link',
  custom_text: 'Custom text',
  footer: 'Footer',
};

export const BLOCK_TYPES: EmailBlockType[] = [
  'brand_header',
  'heading',
  'intro',
  'facts',
  'button',
  'link',
  'custom_text',
  'footer',
];

let counter = 0;

/** A client-side id for React keys / reorder identity - the backend accepts
 * whatever it is handed (Block document contract, PLAN-email-layout-28sep.md). */
export function nextBlockId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  counter += 1;
  return `block-${Date.now()}-${counter}`;
}

export function defaultBlockFor(type: EmailBlockType, id: string): EmailBlock {
  switch (type) {
    case 'brand_header':
      return { id, type };
    case 'heading':
      return { id, type, text: '', align: 'left' };
    case 'intro':
      return { id, type, text: '', align: 'left' };
    case 'facts':
      return { id, type, rows: [], hide_empty: true };
    case 'button':
      return { id, type, label: 'Open', url: '' };
    case 'link':
      return { id, type, label: 'Or paste this link into your browser:', url: '' };
    case 'custom_text':
      return { id, type, html: '' };
    case 'footer':
      return { id, type, note: null };
  }
}

/** A template with no `layout_json` renders as this implicit list (AC-EM040). */
export function buildImplicitBlocks(template: Pick<EmailTemplate, 'body_html'>): EmailBlock[] {
  return [
    { id: nextBlockId(), type: 'brand_header' },
    { id: nextBlockId(), type: 'custom_text', html: template.body_html ?? '' },
    { id: nextBlockId(), type: 'footer', note: null },
  ];
}

/** Every block gets a stable id before it enters the editor, even one loaded
 * from a saved `layout_json` that predates this client (the contract makes
 * `id` optional). */
export function withBlockIds(blocks: EmailBlock[]): EmailBlock[] {
  return blocks.map((block) => (block.id ? block : { ...block, id: nextBlockId() }));
}

/** A short read-only summary for the view-mode row (no UUIDs, no feature
 * explanations - just what the block will show). */
export function summarizeBlock(block: EmailBlock): string {
  switch (block.type) {
    case 'brand_header':
      return 'Logo on the brand band';
    case 'heading':
      return block.text || 'No heading text yet';
    case 'intro':
      return block.text ? block.text.split('\n')[0] : 'No intro text yet';
    case 'facts':
      return block.rows.length ? `${block.rows.length} row(s)` : 'No rows yet';
    case 'button':
      return block.label || 'No label yet';
    case 'link':
      return block.label || 'No label yet';
    case 'custom_text':
      return 'Rich text';
    case 'footer':
      return block.note ? block.note : "Theme's default footer";
  }
}
