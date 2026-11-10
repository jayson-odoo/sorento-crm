'use client';

import type { ReactNode } from 'react';
import RequireAccess from '@/app/components/common/RequireAccess';

/** The Town is admin-only (owner, 10 Nov 2026): the same permission the snapshot endpoint requires. */
export default function TownLayout({ children }: { children: ReactNode }) {
  return <RequireAccess permission="dashboards.town.view">{children}</RequireAccess>;
}
