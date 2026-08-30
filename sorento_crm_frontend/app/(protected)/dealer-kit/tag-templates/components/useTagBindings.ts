'use client';

/**
 * The live data behind bound layers, held in EDITOR state and nowhere else.
 *
 * A saved document carries a binding and any text somebody typed over it; the
 * values arrive from the backend on every open (ADR 0008). That is the whole
 * reason this is a hook and not a field on the document: state that is thrown
 * away on unmount cannot be saved by accident.
 *
 * Shared by the template editor and the tag sheet designer so both resolve a
 * product the same way, and both stop showing a price the moment the promotion
 * behind it ends.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type {
  GroupBinding,
  ProductSetTagData,
  ProductTagData,
  TagBindingData,
} from '@/lib/dealer-kit/tag-template-types';
import { bindingKey } from '@/lib/dealer-kit/tag-template-types';
import { ensureFontsLoaded, ensureSeedFontsLoaded } from '@/lib/dealer-kit/fonts';
import {
  getProductSetTagData,
  getProductTagData,
} from '../../services/tagDataService';
import { listAssets, listFontAssets, type KitAsset } from '../../services/assetService';
import { listSpecKeys } from '../../services/tagDataService';
import type { SpecKeyOption } from '@/lib/dealer-kit/merge-fields';
import { STATIC_FONT_OPTIONS } from './InspectorPanel';

// ---------------------------------------------------------------------------
// Bound product / set data
// ---------------------------------------------------------------------------

export interface TagBindings {
  /** Resolved data by binding key. */
  get: (binding: GroupBinding | undefined) => TagBindingData | null;
  loadProduct: (productId: string) => Promise<ProductTagData | null>;
  loadSet: (setId: string) => Promise<ProductSetTagData | null>;
  /** Resolve every binding a document already carries, on open. */
  loadAll: (bindings: GroupBinding[]) => Promise<void>;
}

export function useTagBindings(promotionId?: string | null): TagBindings {
  const [data, setData] = useState<Record<string, TagBindingData>>({});

  const loadProduct = useCallback(
    async (productId: string) => {
      try {
        const product = await getProductTagData(productId, promotionId);
        setData((prev) => ({
          ...prev,
          [`product:${productId}`]: { kind: 'product', product },
        }));
        return product;
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to load product data',
        );
        return null;
      }
    },
    [promotionId],
  );

  const loadSet = useCallback(
    async (setId: string) => {
      try {
        const set = await getProductSetTagData(setId, promotionId);
        setData((prev) => ({ ...prev, [`set:${setId}`]: { kind: 'set', set } }));
        return set;
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to load product set data',
        );
        return null;
      }
    },
    [promotionId],
  );

  const loadAll = useCallback(
    async (bindings: GroupBinding[]) => {
      const seen = new Set<string>();
      for (const binding of bindings) {
        const key = bindingKey(binding);
        if (!key || seen.has(key)) continue;
        seen.add(key);
        if (binding.product_id) await loadProduct(binding.product_id);
        else if (binding.product_set_id) await loadSet(binding.product_set_id);
      }
    },
    [loadProduct, loadSet],
  );

  const get = useCallback(
    (binding: GroupBinding | undefined) => {
      const key = bindingKey(binding);
      return key ? data[key] ?? null : null;
    },
    [data],
  );

  return { get, loadProduct, loadSet, loadAll };
}

// ---------------------------------------------------------------------------
// The artwork library and brand fonts
// ---------------------------------------------------------------------------

export interface KitLibrary {
  /** assetId -> signed URL, for image and badge layers. */
  assetUrls: Record<string, string>;
  fonts: KitAsset[];
  /** The spec vocabulary the Insert field dialog offers under Specs (D58). */
  specKeys: SpecKeyOption[];
  /** Google fallbacks plus every uploaded brand font. */
  fontOptions: SearchableSelectOption[];
  reload: () => Promise<void>;
  /** Called after an upload, so a new asset is usable without a round trip. */
  remember: (asset: KitAsset) => void;
}

export function useKitLibrary(): KitLibrary {
  const [assets, setAssets] = useState<KitAsset[]>([]);
  const [fonts, setFonts] = useState<KitAsset[]>([]);
  const [specKeys, setSpecKeys] = useState<SpecKeyOption[]>([]);

  const reload = useCallback(async () => {
    try {
      const [all, fontRows] = await Promise.all([listAssets({ limit: 200 }), listFontAssets()]);
      setAssets(all);
      setFonts(fontRows);
    } catch {
      // A library that will not load leaves layers showing their no-image
      // state. It must not stop the canvas opening.
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Fetched once. A registry read that fails leaves the Specs group empty
  // rather than stopping the canvas: every other field still inserts.
  useEffect(() => {
    void listSpecKeys()
      .then(setSpecKeys)
      .catch(() => setSpecKeys([]));
  }, []);

  // The seeded templates' stand-in faces (D32). Loaded unconditionally rather
  // than off the asset list, because they come from a stylesheet rather than
  // from the library - and every one of the eight starter templates is set in
  // them, so a canvas drawn before they arrive lays out in a system sans and
  // never re-measures.
  useEffect(() => {
    void ensureSeedFontsLoaded();
  }, []);

  // Konva measures text against the fonts loaded AT THAT MOMENT, so the faces
  // have to reach the document before a layer using one is drawn.
  useEffect(() => {
    if (fonts.length === 0) return;
    void ensureFontsLoaded(
      fonts
        .filter((font) => font.url)
        .map((font) => ({ name: font.name, family: font.name, url: font.url as string })),
    );
  }, [fonts]);

  const remember = useCallback((asset: KitAsset) => {
    setAssets((prev) => [...prev.filter((a) => a.id !== asset.id), asset]);
    if (asset.kind === 'font') {
      setFonts((prev) => [...prev.filter((a) => a.id !== asset.id), asset]);
    }
  }, []);

  const assetUrls = useMemo(() => {
    const map: Record<string, string> = {};
    for (const asset of assets) {
      if (asset.url) map[asset.id] = asset.url;
    }
    return map;
  }, [assets]);

  const fontOptions = useMemo(() => {
    const brand = fonts.map((font) => ({
      value: font.name,
      label: font.name,
      description: 'Brand font',
    }));
    const known = new Set(brand.map((option) => option.value));
    return [...brand, ...STATIC_FONT_OPTIONS.filter((o) => !known.has(o.value))];
  }, [fonts]);

  return { assetUrls, fonts, specKeys, fontOptions, reload, remember };
}
