'use client';

/**
 * The price tag line editor's behaviour (PLAN-price-tag-combos D2, line pricing D1-D4): the Item
 * pick, the package and part rows, the line's promotion and manual price, and the two lookups that
 * keep them current (combos once per product, one pricing call for every line).
 *
 * Shared by the portal's price tag form and the CRM request page (PORTAL-P4-REQUESTS S7b). The
 * caller owns `lines` (its validation, AI extract and save read them too) and injects the lookups:
 * the portal's go through the portal token, the CRM's through `/api/v1/my-requests`. `lookups` must
 * be a stable object (a module constant), since the effects and callbacks depend on it. Moved out of
 * `app/(auth)/portal/components/PriceTagRequestForm.tsx` unchanged.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type {
  PriceMode,
  ProductCombosLookup,
  TagItemOption,
} from '@/app/(auth)/portal/lib/price-tag-request-service';
import type { LinePricingLineInput, LinePricingResult } from '@/lib/dealer-kit/line-pricing-types';
import { distinctName } from '@/lib/product-display';
import { emptyDraftLine, newPartKey, partsFromCombo, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';

/** The three catalogue calls the editor makes. */
export interface PriceTagLineLookups {
  lookupTagItems: (query?: string) => Promise<TagItemOption[]>;
  lookupProductCombos: (productId: string) => Promise<ProductCombosLookup>;
  lookupLinePricing: (priceMode: PriceMode, lines: LinePricingLineInput[]) => Promise<LinePricingResult[]>;
}

interface Options {
  lines: DraftLine[];
  setLines: Dispatch<SetStateAction<DraftLine[]>>;
  priceMode: PriceMode;
  lookups: PriceTagLineLookups;
}

export function usePriceTagLineEditor({ lines, setLines, priceMode, lookups }: Options) {
  // ---- Line pricing, edit form (D1/D4/S1, mocked - `lookupLinePricing`'s
  // own header documents the eventual real contract) ----
  //
  // One call for every priced line, keyed by the line's own client key. A
  // set line, or a line with no product yet, asks nothing. Recomputes
  // whenever a line's product, parts or chosen promotion change - captured
  // as a signature string so an unrelated edit (quantity, remarks) does not
  // refetch what would come back identical.
  const linesRef = useRef<DraftLine[]>(lines);
  useEffect(() => {
    linesRef.current = lines;
  }, [lines]);
  const [linePricing, setLinePricing] = useState<Record<string, LinePricingResult>>({});
  const pricingSignature = useMemo(
    () =>
      JSON.stringify(
        lines.map((l) => [
          l.key,
          l.line_type,
          l.product_id,
          l.parts.map((p) => [p.product_id, p.candidates.map((c) => c.product_id)]),
          l.promotion_id,
        ]),
      ),
    [lines],
  );
  useEffect(() => {
    const inputs: LinePricingLineInput[] = linesRef.current
      .filter((l) => l.line_type === 'product' && l.product_id)
      .map((l) => ({
        key: l.key,
        product_id: l.product_id,
        part_product_ids: l.parts
          .filter((p) => p.product_id)
          .map((p) => p.product_id as string),
        candidate_product_ids: l.parts.flatMap((p) =>
          p.candidates.map((c) => c.product_id),
        ),
        promotion_id: l.promotion_id,
      }));
    if (inputs.length === 0) {
      setLinePricing({});
      return;
    }
    let cancelled = false;
    lookups.lookupLinePricing(priceMode, inputs).then((results) => {
      if (cancelled) return;
      setLinePricing(Object.fromEntries(results.map((r) => [r.key, r])));
      // D2 (AC-S1-4): pre-fill the line's promotion with the lowest-total
      // covering one, but only once - a line the salesperson has already
      // picked or explicitly cleared (`promotion_locked`) never gets
      // overwritten, and a manual price already typed wins outright.
      setLines((prev) =>
        prev.map((l) => {
          const result = results.find((r) => r.key === l.key);
          if (
            !result ||
            l.promotion_locked ||
            l.promotion_id ||
            l.manual_sell_price != null ||
            !result.auto_promotion_id
          ) {
            return l;
          }
          return { ...l, promotion_id: result.auto_promotion_id };
        }),
      );
    });
    return () => {
      cancelled = true;
    };
    // `linesRef.current` is read fresh inside rather than closed over, so
    // `lines` itself is deliberately not a dependency - `pricingSignature`
    // already fires this whenever a pricing-relevant field changes.
  }, [priceMode, pricingSignature, lookups, setLines]);

  // ---- Line management ----
  const addLine = useCallback(() => {
    setLines((prev) => [...prev, emptyDraftLine()]);
  }, [setLines]);

  const removeLine = useCallback(
    (key: string) => {
      setLines((prev) => prev.filter((l) => l.key !== key));
    },
    [setLines],
  );

  const updateLine = useCallback(
    (key: string, patch: Partial<DraftLine>) => {
      setLines((prev) =>
        prev.map((l) => (l.key === key ? { ...l, ...patch } : l)),
      );
    },
    [setLines],
  );

  // ---- Packages and parts (D2) ----

  /** Which `<line key>:<product id>` pairs have already been asked about, so a
   *  re-render mid-lookup does not fire the same call a second time. Cleared for
   *  a line whenever its item changes - see `handleItemSelect`. */
  const combosAskedRef = useRef<Set<string>>(new Set());

  const forgetCombosAsked = useCallback((key: string) => {
    for (const entry of Array.from(combosAskedRef.current)) {
      if (entry.startsWith(`${key}:`)) combosAskedRef.current.delete(entry);
    }
  }, []);

  /**
   * What the picked product is sold as, asked once per product on a line.
   *
   * An effect rather than a call inside the Item picker, because the same answer
   * is needed for a line that arrived from a reopened draft (AC-S2-9) or from
   * the AI extract, neither of which goes through the picker.
   *
   * A single combo is applied on the spot (AC-S2-1) - but only on a line that
   * has neither a package nor any parts yet, so reopening a draft whose parts
   * were edited by hand does not quietly put the removed ones back.
   */
  useEffect(() => {
    const pending = lines.filter(
      (l) =>
        l.line_type === 'product' &&
        l.product_id &&
        !l.combos_loaded &&
        !combosAskedRef.current.has(`${l.key}:${l.product_id}`),
    );
    if (pending.length === 0) return;
    for (const line of pending) {
      const productId = line.product_id as string;
      combosAskedRef.current.add(`${line.key}:${productId}`);
      lookups
        .lookupProductCombos(productId)
        .then((lookup) => {
          setLines((prev) =>
            prev.map((l) => {
              if (l.key !== line.key || l.product_id !== productId) return l;
              const autoApply =
                !l.combo_id && l.parts.length === 0 && lookup.combos.length === 1;
              return {
                ...l,
                combos_loaded: true,
                combos: lookup.combos,
                host_guarded: lookup.host_guarded,
                ...(autoApply
                  ? {
                      combo_id: lookup.combos[0].combo_id,
                      parts: partsFromCombo(lookup.combos[0]),
                    }
                  : {}),
              };
            }),
          );
        })
        .catch(() => {
          // A lookup that fails must not hold up the line: it offers no package
          // and no warning, which is exactly a product that has none.
          setLines((prev) =>
            prev.map((l) =>
              l.key === line.key && l.product_id === productId
                ? { ...l, combos_loaded: true }
                : l,
            ),
          );
        });
    }
  }, [lines, lookups, setLines]);

  /** The Package select on a line with two or more combos (AC-S2-2). Clearing it
   *  takes the parts with it - they belonged to the package. */
  const choosePackage = useCallback(
    (key: string, comboId: string) => {
      setLines((prev) =>
        prev.map((l) => {
          if (l.key !== key) return l;
          const combo = l.combos.find((c) => c.combo_id === comboId);
          return combo
            ? { ...l, combo_id: combo.combo_id, parts: partsFromCombo(combo) }
            : { ...l, combo_id: null, parts: [] };
        }),
      );
    },
    [setLines],
  );

  /** The line's Promotion select (AC-S1-3..S1-7). Picking one clears any
   *  manual price (they are mutually exclusive, D2); clearing it (empty
   *  string, `SearchableSelect`'s own clear) restores the manual input,
   *  empty. Either way the pick is now deliberate, so future pricing
   *  answers never auto-fill over it again. */
  const choosePromotion = useCallback(
    (key: string, promotionId: string) => {
      setLines((prev) =>
        prev.map((l) =>
          l.key === key
            ? {
                ...l,
                promotion_id: promotionId || null,
                promotion_locked: true,
                manual_sell_price: null,
              }
            : l,
        ),
      );
    },
    [setLines],
  );

  /** The "Type a price" input, only shown while the line has no promotion
   *  (AC-S1-6). Empty clears it back to nothing typed. */
  const setManualSellPrice = useCallback(
    (key: string, value: number | null) => {
      setLines((prev) =>
        prev.map((l) => (l.key === key ? { ...l, manual_sell_price: value } : l)),
      );
    },
    [setLines],
  );

  /** Staged removal (AC-S2-4): the part row is unsaved form state, not a record,
   *  so it goes on the click with no countdown and no confirm - the same way a
   *  line row already does. */
  const removePart = useCallback(
    (key: string, partKeyToRemove: string) => {
      setLines((prev) =>
        prev.map((l) =>
          l.key === key
            ? { ...l, parts: l.parts.filter((part) => part.key !== partKeyToRemove) }
            : l,
        ),
      );
    },
    [setLines],
  );

  /** D19: put back exactly what a "Missing" warning names - the fixed parts
   *  and choice groups the line's chosen combo has that it does not already
   *  hold (resolved when the group has one candidate, open otherwise, same
   *  as the initial pick). Rows the salesperson kept are untouched. */
  const restoreParts = useCallback(
    (key: string) => {
      setLines((prev) =>
        prev.map((l) => {
          if (l.key !== key || !l.combo_id) return l;
          const combo = l.combos.find((c) => c.combo_id === l.combo_id);
          if (!combo) return l;
          const missing = partsFromCombo(combo).filter((candidate) =>
            candidate.role
              ? !l.parts.some((row) => row.role === candidate.role)
              : !l.parts.some((row) => row.product_id === candidate.product_id),
          );
          return missing.length > 0 ? { ...l, parts: [...l.parts, ...missing] } : l;
        }),
      );
    },
    [setLines],
  );

  /** An open row's candidate select (AC-S2-3): picking resolves the row, clearing
   *  reopens it, which is why `candidates` stays on the row either way. */
  const resolvePart = useCallback(
    (key: string, partKeyToResolve: string, productId: string) => {
      setLines((prev) =>
        prev.map((l) => {
          if (l.key !== key) return l;
          return {
            ...l,
            parts: l.parts.map((part) => {
              if (part.key !== partKeyToResolve) return part;
              const chosen = part.candidates.find(
                (candidate) => candidate.product_id === productId,
              );
              return chosen
                ? { ...part, product_id: chosen.product_id, code: chosen.code, name: chosen.name }
                : { ...part, product_id: null, code: '', name: '' };
            }),
          };
        }),
      );
    },
    [setLines],
  );

  /** A part added by hand, on any line, combo or not (AC-S2-4). */
  const addPart = useCallback(
    (key: string, option: SearchableSelectOption | null) => {
      if (!option) return;
      const [kind, id] = option.value.split(':');
      if (kind !== 'product') return;
      const code = (option.description ?? '').split(' - ').slice(1).join(' - ');
      setLines((prev) =>
        prev.map((l) => {
          if (l.key !== key) return l;
          if (l.parts.some((part) => part.product_id === id)) return l;
          return {
            ...l,
            parts: [
              ...l.parts,
              {
                key: newPartKey(),
                product_id: id,
                code,
                name: option.label,
                role: null,
                candidates: [],
              },
            ],
          };
        }),
      );
    },
    [setLines],
  );

  // ---- Item options: sets and products in ONE list (D47) ----
  // The label carries the word Set or Product, because the two look alike in a
  // dropdown and picking the wrong one produces a different tag.
  const fetchItemOptions = useCallback(
    async (query: string): Promise<SearchableSelectOption[]> => {
      const items = await lookups.lookupTagItems(query);
      return items.map((i) => ({
        value: `${i.kind}:${i.id}`,
        label: i.name || i.code,
        description: distinctName(i.code, i.name)
          ? `${i.kind === 'product_set' ? 'Set' : 'Product'} - ${i.code}`
          : i.kind === 'product_set'
            ? 'Set'
            : 'Product',
      }));
    },
    [lookups],
  );

  /** The same catalogue lookup the Item picker uses, products only: a part is a
   *  product, never a set. */
  const fetchPartOptions = useCallback(
    async (query: string): Promise<SearchableSelectOption[]> => {
      const items = await lookups.lookupTagItems(query);
      return items
        .filter((i) => i.kind === 'product')
        .map((i) => ({
          value: `product:${i.id}`,
          label: i.name || i.code,
          description: distinctName(i.code, i.name) ? `Product - ${i.code}` : undefined,
        }));
    },
    [lookups],
  );

  // ---- One picker, both kinds (D47) ----
  // The chosen option decides the line's type; the payload the server reads is
  // unchanged, still line_type plus whichever of the two ids matches it.
  const handleItemSelect = useCallback(
    (key: string, option: SearchableSelectOption | null) => {
      // The combos lookup remembers what it has already asked about, so the
      // memory has to be forgotten the moment the row points somewhere else -
      // otherwise re-picking a product this line held before left it
      // `combos_loaded: false` forever, with no Package select, no parts and no
      // warning (review round 2, S1).
      forgetCombosAsked(key);
      if (!option) {
        updateLine(key, {
          product_id: null,
          product_set_id: null,
          name: '',
          code: '',
          guard_error: null,
          // The package belonged to the product that just went away.
          combo_id: null,
          combos: [],
          combos_loaded: false,
          host_guarded: false,
          parts: [],
          // So did any price basis - it was for the product that left.
          promotion_id: null,
          promotion_locked: false,
          manual_sell_price: null,
          pricing: null,
        });
        return;
      }
      const [kind, id] = option.value.split(':');
      const isSet = kind === 'product_set';
      const code = (option.description ?? '').split(' - ').slice(1).join(' - ');
      // R3-7: refuse a product/set already on another line, inline - the
      // same guard the backend now enforces (DUPLICATE_LINE), so a save
      // never round-trips just to be told this.
      const duplicate = lines.some(
        (l) =>
          l.key !== key &&
          (isSet ? l.product_set_id === id : l.product_id === id),
      );
      if (duplicate) {
        updateLine(key, {
          guard_error: `${code || option.label} is already on this request.`,
        });
        return;
      }
      updateLine(key, {
        line_type: isSet ? 'product_set' : 'product',
        product_id: isSet ? null : id,
        product_set_id: isSet ? id : null,
        name: option.label,
        // The description reads "Set - CODE" / "Product - CODE"; the code is what
        // the row shows, so it is stored without the word in front of it.
        code,
        guard_error: null,
        // A set is printed as one thing and carries no package (D2: a cabinet
        // request never mixes set and combo on one line), so both kinds reset
        // here and only a product goes on to ask what it is sold as - the effect
        // above picks it up off `combos_loaded`.
        combo_id: null,
        combos: [],
        combos_loaded: isSet,
        host_guarded: false,
        parts: [],
        // A different product invalidates any promotion or manual price the
        // old one carried - the pricing effect re-asks for the new one.
        promotion_id: null,
        promotion_locked: false,
        manual_sell_price: null,
        pricing: null,
      });
    },
    [forgetCombosAsked, updateLine, lines],
  );

  return {
    linePricing,
    addLine,
    removeLine,
    updateLine,
    handleItemSelect,
    choosePackage,
    choosePromotion,
    setManualSellPrice,
    removePart,
    restoreParts,
    resolvePart,
    addPart,
    fetchItemOptions,
    fetchPartOptions,
  };
}

export type PriceTagLineEditor = ReturnType<typeof usePriceTagLineEditor>;
