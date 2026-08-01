'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { Project } from '../../_shared/types/project.types';

/**
 * Delivery schedules (P6, contract section 4).
 *
 * Placeholder wired into the detail page's tabs so the destination exists while the
 * slice is built. Replace the body; keep the export name and the props.
 */
export function DeliverySchedulesPanel({ project }: { project: Project }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Delivery schedules</CardTitle>
      </CardHeader>
      <CardContent className="py-10 text-center text-sm text-muted-foreground">
        Not built yet.
      </CardContent>
    </Card>
  );
}
