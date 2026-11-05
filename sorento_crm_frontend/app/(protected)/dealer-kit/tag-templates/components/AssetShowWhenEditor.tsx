'use client';

/**
 * Feature icons (PRICETAG-DESIGNER-GAPS item 3, F6): an icon's "Show when" rule, edited in the
 * asset library. A spec (active registry keys with a fixed set of values) and the value(s) that
 * show the icon; clearing the spec clears the rule.
 */
import { useMemo, useState } from 'react';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useFeatureIconSpecKeys, useSetAssetShowWhen } from '../../hooks/useFeatureIcons';
import type { KitAsset } from '../../services/assetService';

interface AssetShowWhenEditorProps {
  asset: KitAsset;
  onBack: () => void;
  onSaved: (asset: KitAsset) => void;
}

export function AssetShowWhenEditor({
  asset,
  onBack,
  onSaved,
}: AssetShowWhenEditorProps) {
  const registry = useFeatureIconSpecKeys();
  const save = useSetAssetShowWhen();
  const [specKey, setSpecKey] = useState(asset.show_when_spec_key ?? '');
  const [values, setValues] = useState<string[]>(asset.show_when_values ?? []);

  // Only a key with a fixed set of values can carry a rule (the server refuses any other): a
  // yes/no key reads `true` / `false`, any other its registry values.
  const keys = useMemo(
    () =>
      (registry.data ?? []).filter(
        (key) => key.data_type === 'boolean' || (key.allowed_values ?? []).length > 0,
      ),
    [registry.data],
  );
  const specOptions = useMemo(
    () => keys.map((key) => ({ value: key.key, label: key.label })),
    [keys],
  );
  const chosen = keys.find((key) => key.key === specKey);
  // Labels come from the server, the same reading a tag prints ("Cold Only"), so this list
  // and the product screens cannot word a value differently (crew pass, 5 Nov).
  const valueOptions = useMemo(() => chosen?.value_options ?? [], [chosen]);

  const canSave = !save.isPending && (specKey === '' || values.length > 0);

  const handleSave = () => {
    save.mutate(
      {
        id: asset.id,
        body: { spec_key: specKey || null, values: specKey ? values : [] },
      },
      { onSuccess: onSaved },
    );
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          mode="icon"
          aria-label="Back to the library"
          onClick={onBack}
        >
          <ArrowLeft className="size-4" />
        </Button>
        <span className="truncate text-sm font-medium" title={asset.name}>
          {asset.name}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Show when</Label>
        <SearchableSelect
          aria-label="Show when spec"
          placeholder="Always hidden"
          size="sm"
          clearable
          value={specKey}
          loadError={registry.error}
          onChange={(next: string) => {
            setSpecKey(next ?? '');
            setValues([]);
          }}
          options={specOptions}
        />
      </div>
      {specKey && (
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Is</Label>
          <SearchableMultiSelect
            aria-label="Show when values"
            size="sm"
            clearable
            value={values}
            onChange={setValues}
            options={valueOptions}
          />
        </div>
      )}
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          className="h-7 text-xs"
          disabled={!canSave}
          onClick={handleSave}
        >
          {save.isPending && <Loader2 className="mr-1 size-3.5 animate-spin" />}
          Save
        </Button>
      </div>
    </div>
  );
}
