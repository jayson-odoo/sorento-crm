'use client';

/**
 * An existing combo's price tag templates, edited in place on the product page
 * (PRICETAG-LPSP). Drawn only for `dealer_kit.tag_templates.manage`; each change saves at once
 * through the combo PUT, like the product's own templates card. Unticking one is an unlink, so it
 * parks with a countdown and a Cancel and the server commits it (`combo.unlink_tag_templates`).
 */

import { useEffect, useState } from 'react';
import { clickToken } from '@/lib/click-token';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { ComboTemplatesPicker } from './ComboTemplatesPicker';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  comboTagTemplatesKey,
  useComboTagTemplates,
  useSetComboTagTemplates,
} from '@/app/(protected)/dealer-kit/hooks/useProductTagTemplates';
import { explicitDefaultId } from '@/app/(protected)/dealer-kit/services/productTagTemplateService';

function ComboTemplatesEditor({ comboId }: { comboId: string }) {
  const linked = useComboTagTemplates(comboId);
  const save = useSetComboTagTemplates();
  const rows = linked.data ?? [];
  const [unlink, setUnlink] = useState<{ batchId: string; ids: string[]; subject: string } | null>(
    null,
  );
  const unlinking = useDeferredAction({
    actionKey: 'combo.unlink_tag_templates',
    entityType: 'combo',
    entityId: unlink ? comboId : null,
    verb: 'Unlinking',
    subject: unlink?.subject ?? '',
    surface: 'toast',
    successMessage: 'Template unlinked',
    payload: { template_ids: unlink?.ids ?? [] },
    invalidateKeys: [comboTagTemplatesKey(comboId)],
  });
  useEffect(() => {
    if (unlink) unlinking.start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unlink?.batchId]);

  if (linked.isLoading || linked.isError) return null;
  const current = rows.map((row) => row.id);
  return (
    <div className="border-b p-3">
      <ComboTemplatesPicker
        idPrefix={`combo-${comboId}`}
        value={current}
        defaultId={explicitDefaultId(rows) ?? ''}
        selectedOptions={rows.map((row) => ({ value: row.id, label: row.name }))}
        disabled={save.isPending || unlinking.isPending}
        onChange={(ids, defaultId) => {
          const removed = current.filter((id) => !ids.includes(id));
          const added = ids.filter((id) => !current.includes(id));
          if (removed.length > 0) {
            const names = rows.filter((row) => removed.includes(row.id)).map((row) => row.name);
            setUnlink({
              batchId: clickToken(),
              ids: removed,
              subject: names.length === 1 ? names[0] : `${names.length} templates`,
            });
            return;
          }
          // An add (or a new default) saves at once; the removed ones go through the countdown.
          const all = [...current, ...added];
          save.mutate({
            combo_id: comboId,
            template_ids: all,
            default_template_id: all.length > 1 && defaultId ? defaultId : null,
          });
        }}
      />
    </div>
  );
}

export function ComboTemplatesField({ comboId }: { comboId: string }) {
  const canManage = useHasPermission('dealer_kit.tag_templates.manage');
  return canManage ? <ComboTemplatesEditor comboId={comboId} /> : null;
}

export default ComboTemplatesField;
