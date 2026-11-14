'use client';

import { useUiVersion } from './useUiVersion';

/** The avatar-menu item that switches between the two versions (B-7, B-8). */
export function VersionSwitchItem({ className }: { className?: string }) {
  const { uiVersion, uiV2Available, setUiVersion } = useUiVersion();
  if (!uiV2Available) return null;
  const toV2 = uiVersion === 'v1';
  return (
    <button
      type="button"
      role="menuitem"
      className={className ?? 'w-full text-start'}
      onClick={() => void setUiVersion(toV2 ? 'v2' : 'v1')}
    >
      {toV2 ? 'Switch to the new version' : 'Switch to the previous version'}
    </button>
  );
}
