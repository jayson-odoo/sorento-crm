'use client';

import { useEffect } from 'react';
import {
  clearCurrentEntity,
  setCurrentEntity,
} from '@/lib/aiEntityContext';

/**
 * RecordEntityRegistrar - registers the record the user is currently viewing
 * into the module-level AI entity store, so the AI assistant can ground answers
 * (e.g. "Why was this complaint rejected?") in the active record.
 *
 * Mount it on a detail page (or inside a record-scoped modal). Registers on
 * mount, re-registers when entityType/id change, and clears on unmount.
 *
 * Guard: a "new"/empty id is not a real record - skip registration (and clear
 * any stale entry) so a create flow doesn't leak a phantom record.
 */
export default function RecordEntityRegistrar({
  entityType,
  id,
}: {
  entityType: string;
  id: string;
}) {
  useEffect(() => {
    if (!id || id === 'new') {
      clearCurrentEntity();
      return;
    }
    setCurrentEntity({ entity_type: entityType, id });
    return () => {
      clearCurrentEntity();
    };
  }, [entityType, id]);

  return null;
}
