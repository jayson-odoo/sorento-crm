'use client';

import type { ReactNode } from 'react';
import { useUiVersion } from './useUiVersion';

/** Renders exactly one side by the effective version (B-12). Reads context only. */
export function Versioned({ v1, v2 }: { v1: ReactNode; v2: ReactNode }) {
  const { uiVersion } = useUiVersion();
  return <>{uiVersion === 'v2' ? v2 : v1}</>;
}
