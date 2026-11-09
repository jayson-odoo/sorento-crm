/**
 * Shared fixtures for the PRICETAG-UPGRADE-VARIANTS tests (not a test file). Real-looking codes:
 * SRTKS2432 sink (combo SP 949, LP 1150), SRTKT71SS upgrade (top-up 150, LP 440) and the
 * SRTWC8354-SH family. Everything is typed loosely on purpose: the new optional fields do not
 * exist on the types yet.
 */
import type { FeatureIcon } from '../feature-icons';
import type { TagBindingData } from '../tag-template-types';

export const spec = (key: string, value: string, raw?: string) => ({
  key,
  label: key,
  value,
  unit: null,
  raw: raw ?? value,
});

export const icon = (id: string, name: string, spec_key: string, values: string[]): FeatureIcon => ({
  id,
  name,
  spec_key,
  values,
});

/** Registry order: steel grade, then trap length 150/200/250, then p-trap, then UF seat. */
export const TRAP_ICONS: FeatureIcon[] = [
  icon('i6', '6in S-trap 150mm', 'trap_length', ['150']),
  icon('i8', '8in S-trap 200mm', 'trap_length', ['200']),
  icon('i10', '10in S-trap 250mm', 'trap_length', ['250']),
  icon('ip', 'P-trap 180mm', 'trap_type', ['p_trap']),
  icon('iuf', 'UF seat cover', 'seat_material', ['uf']),
];

export const SUS_ICON = icon('sus', 'SUS 304', 'steel_grade', ['304']);

export const UPGRADE_SPECS = [spec('steel_grade', 'SUS 304', '304')];

function slotRow(code: string, list: number | null, extra: Record<string, unknown> = {}) {
  return {
    product_id: `id-${code}`,
    code,
    name: `Name ${code}`,
    dimensions: '',
    list_price: list,
    sell_price: null,
    images: [
      { attachment_id: `alt-${code}`, url: `https://cdn/${code}-2.jpg`, is_primary: false },
      { attachment_id: `att-${code}`, url: `https://cdn/${code}.jpg`, is_primary: true },
    ],
    specs: [],
    currency: 'MYR',
    ...extra,
  };
}

export interface SinkOptions {
  picked?: boolean;
  combo?: boolean;
  topup?: number | null;
  sellPrice?: number | null;
  inSlots?: boolean;
  main?: boolean;
}

/** A request line for SRTKS2432 with the SRTKT71SS upgrade on offer. */
export function sinkLine(opts: SinkOptions = {}): TagBindingData {
  const { picked = false, combo = true, topup = 150, sellPrice = 949, inSlots = true } = opts;
  const upgradeRow = slotRow('SRTKT71SS', 440, { specs: UPGRADE_SPECS, chosen: picked });
  return {
    kind: 'line',
    line: {
      tag_id: 't1',
      line_id: 'l1',
      tag_label: '1a',
      open_groups: [],
      parts: [],
      code: 'SRTKS2432',
      name: 'Sink',
      dimensions: '',
      spec_lines: '',
      specs: [],
      set_members: '',
      images: [],
      list_price: 1150,
      sell_price: sellPrice,
      show_promo_price: true,
      included_accessories: '',
      quantity: 1,
      barcode: null,
      combo: combo
        ? {
            id: 'c1',
            name: 'Sink pack',
            description: null,
            free_items: '',
            choices: [],
            upgrades: [
              {
                product_id: 'id-SRTKT71SS',
                code: 'SRTKT71SS',
                description: 'Pull-out shower mixer',
                topup_amount: topup,
                picked,
              },
            ],
          }
        : null,
      slots: combo
        ? {
            fixed: [slotRow('SRTKT1862SS', 285)],
            groups: [],
            upgrades: inSlots ? [{ ...upgradeRow, topup_amount: topup }] : [],
          }
        : null,
    },
  } as unknown as TagBindingData;
}

/** A request line for the SRTWC8354-SH family tag. */
export function familyLine(
  variants: { code: string; specs: ReturnType<typeof spec>[] }[],
  ownSpecs: ReturnType<typeof spec>[] = [spec('trap_length', '250', '250'), spec('trap_type', 'S Trap', 's_trap')],
): TagBindingData {
  return {
    kind: 'line',
    line: {
      tag_id: 't1',
      line_id: 'l1',
      tag_label: '1a',
      open_groups: [],
      parts: [],
      code: 'SRTWC8354-SH',
      name: 'WC',
      dimensions: '',
      spec_lines: '',
      specs: ownSpecs,
      set_members: '',
      images: [],
      list_price: 1750,
      sell_price: 799,
      show_promo_price: true,
      included_accessories: '',
      quantity: 1,
      barcode: null,
      variants: variants.map((v) => ({ product_id: `id-${v.code}`, ...v })),
    },
  } as unknown as TagBindingData;
}

export const FAMILY_VARIANTS = [
  { code: 'SRTWC8354-SH-150', specs: [spec('trap_length', '150', '150'), spec('trap_type', 'S Trap', 's_trap')] },
  { code: 'SRTWC8354-SH-200', specs: [spec('trap_length', '200', '200'), spec('trap_type', 'S Trap', 's_trap')] },
  { code: 'SRTWC8354-SH-P', specs: [spec('trap_length', '180', '180'), spec('trap_type', 'P Trap', 'p_trap')] },
  {
    code: 'SRTWC8354-SH-UF',
    specs: [spec('trap_length', '250', '250'), spec('trap_type', 'S Trap', 's_trap'), spec('seat_material', 'UF', 'uf')],
  },
];
