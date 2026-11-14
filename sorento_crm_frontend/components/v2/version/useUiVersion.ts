'use client';

import { useContext } from 'react';
import { UiVersionContext, type UiVersionState } from './context';

/** The one place a component reads the UI version (B-12): context only, never a fetch. */
export function useUiVersion(): UiVersionState {
  return useContext(UiVersionContext);
}
