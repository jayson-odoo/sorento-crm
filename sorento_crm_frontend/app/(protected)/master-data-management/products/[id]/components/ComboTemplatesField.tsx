'use client';

/**
 * An existing combo's price tag templates, edited in place on the product page
 * (PRICETAG-LPSP). Drawn only for `dealer_kit.tag_templates.manage`; each change saves at once
 * through the combo PUT, like the product's own templates card.
 */

import { ComboTemplatesPicker } from './ComboTemplatesPicker';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  useComboTagTemplates,
  useSetComboTagTemplates,
} from '@/app/(protected)/dealer-kit/hooks/useProductTagTemplates';
import { explicitDefaultId } from '@/app/(protected)/dealer-kit/services/productTagTemplateService';

function ComboTemplatesEditor({ comboId }: { comboId: string }) {
  const linked = useComboTagTemplates(comboId);
  const save = useSetComboTagTemplates();
  const rows = linked.data ?? [];
  if (linked.isLoading || linked.isError) return null;
  return (
    <div className="border-b p-3">
      <ComboTemplatesPicker
        idPrefix={`combo-${comboId}`}
        value={rows.map((row) => row.id)}
        defaultId={explicitDefaultId(rows) ?? ''}
        selectedOptions={rows.map((row) => ({ value: row.id, label: row.name }))}
        disabled={save.isPending}
        onChange={(ids, defaultId) =>
          save.mutate({
            combo_id: comboId,
            template_ids: ids,
            default_template_id: ids.length > 1 && defaultId ? defaultId : null,
          })
        }
      />
    </div>
  );
}

export function ComboTemplatesField({ comboId }: { comboId: string }) {
  const canManage = useHasPermission('dealer_kit.tag_templates.manage');
  return canManage ? <ComboTemplatesEditor comboId={comboId} /> : null;
}

export default ComboTemplatesField;
