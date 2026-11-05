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
import { useQuery } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type {
  GroupBinding,
  ProductSetTagData,
  ProductTagData,
  TagBindingData,
} from '@/lib/dealer-kit/tag-template-types';
import { bindingKey } from '@/lib/dealer-kit/tag-template-types';
import { kitLibraryClient, resetKitLibraryCache } from '@/lib/dealer-kit/kit-library-cache';
import type { FeatureIcon } from '@/lib/dealer-kit/feature-icons';
import {
  ensureFontsLoaded,
  ensureSeedFontsLoaded,
} from '@/lib/dealer-kit/fonts';
import {
  getProductSetTagData,
  getProductTagData,
} from '../../services/tagDataService';
import {
  fontAssetUrl,
  listAssets,
  listFontAssets,
  type KitAsset,
} from '../../services/assetService';
import {
  listFeatureIcons,
  listSpecKeys,
  type FeatureIconWithUrl,
} from '../../services/tagDataService';
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

/**
 * Failed resolutions already toasted, by binding key ("product:<id>" /
 * "set:<id>"). Module-level rather than hook state: a line switch remounts
 * `TagCanvasEditor` (a fresh `useTagBindings` instance), and `loadAll`
 * re-resolves the same carried binding on every mount - so a line whose
 * product 404s (a cross-company reference, see `457_ptag_line_xco_repair`)
 * toasted once per remount / retry, a stack for the same product. ONE toast
 * survives for as long as this module does; a later SUCCESSFUL resolve clears
 * the id, so a transient failure never permanently silences a real one.
 */
const _toastedResolutionFailures = new Set<string>();

function toastResolutionFailureOnce(key: string, message: string): void {
  if (_toastedResolutionFailures.has(key)) return;
  _toastedResolutionFailures.add(key);
  toast.error(message);
}

/**
 * One toast per family whose face rejected, for the same reason
 * `_toastedResolutionFailures` is per-key rather than per-call: `useKitLibrary`
 * remounts on a line switch, and `ensureFontsLoaded` re-tries a failed face on
 * every call (S1), so without a dedupe a font that never loads would toast on
 * every reload.
 */
const _toastedFontFailures = new Set<string>();

function toastFontFailureOnce(family: string): void {
  if (_toastedFontFailures.has(family)) return;
  _toastedFontFailures.add(family);
  toast.error(`Font ${family} could not be loaded`);
}

/** Tests only - the module-level dedupe sets are per tab, and a test is one tab. */
export function resetTagBindingsToastDedupeForTests(): void {
  _toastedResolutionFailures.clear();
  _toastedFontFailures.clear();
}

export function useTagBindings(promotionId?: string | null): TagBindings {
  const [data, setData] = useState<Record<string, TagBindingData>>({});

  const loadProduct = useCallback(
    async (productId: string) => {
      const key = `product:${productId}`;
      try {
        const product = await getProductTagData(productId, promotionId);
        _toastedResolutionFailures.delete(key);
        setData((prev) => ({ ...prev, [key]: { kind: 'product', product } }));
        return product;
      } catch (error) {
        toastResolutionFailureOnce(
          key,
          error instanceof Error
            ? error.message
            : 'Failed to load product data',
        );
        return null;
      }
    },
    [promotionId],
  );

  const loadSet = useCallback(
    async (setId: string) => {
      const key = `set:${setId}`;
      try {
        const set = await getProductSetTagData(setId, promotionId);
        _toastedResolutionFailures.delete(key);
        setData((prev) => ({ ...prev, [key]: { kind: 'set', set } }));
        return set;
      } catch (error) {
        toastResolutionFailureOnce(
          key,
          error instanceof Error
            ? error.message
            : 'Failed to load product set data',
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
      return key ? (data[key] ?? null) : null;
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
  /** assetId -> a screen rendition (thumbnail or medium), for a host that must never draw originals. */
  thumbUrls: Record<string, string>;
  fonts: KitAsset[];
  /** The spec vocabulary the Insert field dialog offers under Specs (D58). */
  specKeys: SpecKeyOption[];
  /** Feature icons: every icon each spec value carries, in display order (one per value). */
  featureIcons: FeatureIcon[];
  /** Google fallbacks plus every uploaded brand font. */
  fontOptions: SearchableSelectOption[];
  reload: () => Promise<void>;
  /** Called after an upload, so a new asset is usable without a round trip. */
  remember: (asset: KitAsset) => void;
  /** Called after a successful rename, so the dropdown's label updates in place. */
  rename: (id: string, name: string) => void;
  /** Called after a successful delete, so the dropdown drops the option. */
  forget: (id: string) => void;
}

const libraryClient = kitLibraryClient;
const ASSETS_KEY = ['dealer-kit', 'library', 'assets'] as const;
const FONTS_KEY = ['dealer-kit', 'library', 'fonts'] as const;
/** Feature icons: the spec-value icon list the print page gets too, with signed URLs. */
export const FEATURE_ICONS_KEY = ['dealer-kit', 'library', 'feature-icons'] as const;
const NO_FEATURE_ICONS: FeatureIconWithUrl[] = [];
const SPEC_KEYS_KEY = ['dealer-kit', 'library', 'spec-keys'] as const;
export { resetKitLibraryCache };
const NO_ASSETS: KitAsset[] = [];
const NO_SPEC_KEYS: SpecKeyOption[] = [];

export function useKitLibrary(): KitLibrary {
  // A library that will not load leaves layers showing their no-image state; it must not stop the
  // canvas opening, so a failed read is simply empty data.
  const assetsQuery = useQuery(
    { queryKey: ASSETS_KEY, queryFn: () => listAssets({ limit: 200 }) },
    libraryClient,
  );
  const fontsQuery = useQuery(
    { queryKey: FONTS_KEY, queryFn: () => listFontAssets() },
    libraryClient,
  );
  const featureIconsQuery = useQuery(
    { queryKey: FEATURE_ICONS_KEY, queryFn: async () => listFeatureIcons() },
    libraryClient,
  );
  // A registry read that fails leaves the Specs group empty rather than stopping the canvas.
  const specKeysQuery = useQuery(
    {
      queryKey: SPEC_KEYS_KEY,
      queryFn: () => listSpecKeys().catch(() => NO_SPEC_KEYS),
    },
    libraryClient,
  );
  const assets = assetsQuery.data ?? NO_ASSETS;
  const fonts = fontsQuery.data ?? NO_ASSETS;
  const iconRows = featureIconsQuery.data ?? NO_FEATURE_ICONS;
  const specKeys = specKeysQuery.data ?? NO_SPEC_KEYS;

  const reload = useCallback(async () => {
    await Promise.all([
      libraryClient.refetchQueries({ queryKey: ASSETS_KEY }),
      libraryClient.refetchQueries({ queryKey: FONTS_KEY }),
      libraryClient.refetchQueries({ queryKey: FEATURE_ICONS_KEY }),
    ]);
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
  // have to reach the document before a layer using one is drawn. The URL is
  // built from the asset id, not read off `font.url` (a signed CDN link with
  // no CORS header on some hosts, which `FontFace.load()` rejects outright -
  // see `fontAssetUrl`'s docstring).
  useEffect(() => {
    if (fonts.length === 0) return;
    let cancelled = false;
    void ensureFontsLoaded(
      fonts.map((font) => ({
        name: font.name,
        family: font.name,
        url: fontAssetUrl(font.id),
      })),
    ).then(({ failed }) => {
      if (cancelled) return;
      for (const family of failed) toastFontFailureOnce(family);
    });
    return () => {
      cancelled = true;
    };
  }, [fonts]);

  const remember = useCallback((asset: KitAsset) => {
    libraryClient.setQueryData<KitAsset[]>(ASSETS_KEY, (prev) => [
      ...(prev ?? []).filter((a) => a.id !== asset.id),
      asset,
    ]);
    if (asset.kind === 'font') {
      libraryClient.setQueryData<KitAsset[]>(FONTS_KEY, (prev) => [
        ...(prev ?? []).filter((a) => a.id !== asset.id),
        asset,
      ]);
    }
  }, []);

  /** The row's name changed on the server; carry it here without a round trip. */
  const rename = useCallback((id: string, name: string) => {
    const apply = (prev?: KitAsset[]) =>
      (prev ?? []).map((a) => (a.id === id ? { ...a, name } : a));
    libraryClient.setQueryData<KitAsset[]>(ASSETS_KEY, apply);
    libraryClient.setQueryData<KitAsset[]>(FONTS_KEY, apply);
    libraryClient.setQueryData<FeatureIconWithUrl[]>(FEATURE_ICONS_KEY, (prev) =>
      (prev ?? []).map((icon) => (icon.id === id ? { ...icon, name } : icon)),
    );
  }, []);

  /** The row was deleted on the server; drop it from every list it was in. */
  const forget = useCallback((id: string) => {
    const apply = (prev?: KitAsset[]) =>
      (prev ?? []).filter((a) => a.id !== id);
    libraryClient.setQueryData<KitAsset[]>(ASSETS_KEY, apply);
    libraryClient.setQueryData<KitAsset[]>(FONTS_KEY, apply);
    libraryClient.setQueryData<FeatureIconWithUrl[]>(FEATURE_ICONS_KEY, (prev) =>
      (prev ?? []).filter((icon) => icon.id !== id),
    );
  }, []);

  const assetUrls = useMemo(() => {
    const map: Record<string, string> = {};
    for (const icon of iconRows) {
      if (icon.url) map[icon.id] = icon.url;
    }
    for (const asset of assets) {
      if (asset.url) map[asset.id] = asset.url;
    }
    return map;
  }, [assets, iconRows]);

  const thumbUrls = useMemo(() => {
    const map: Record<string, string> = {};
    for (const asset of assets) {
      if (asset.thumb_url) map[asset.id] = asset.thumb_url;
    }
    return map;
  }, [assets]);

  // The rule only (id, name, spec_key, values); the URL went into `assetUrls` above.
  const featureIcons = useMemo<FeatureIcon[]>(
    () => iconRows.map(({ id, name, spec_key, values }) => ({ id, name, spec_key, values })),
    [iconRows],
  );

  const fontOptions = useMemo(() => {
    const brand = fonts.map((font) => ({
      value: font.name,
      label: font.name,
      description: 'Brand font',
    }));
    const known = new Set(brand.map((option) => option.value));
    return [
      ...brand,
      ...STATIC_FONT_OPTIONS.filter((o) => !known.has(o.value)),
    ];
  }, [fonts]);

  return {
    assetUrls,
    thumbUrls,
    fonts,
    specKeys,
    featureIcons,
    fontOptions,
    reload,
    remember,
    rename,
    forget,
  };
}
