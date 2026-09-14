'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SpecVisibilitySection } from '@/components/spec-visibility/SpecVisibilitySection';

/**
 * Settings -> Spec Visibility (PLAN-spec-visibility-policy, S1).
 *
 * The bottom of the resolution chain: which product spec keys the chatbot reveals
 * when neither the contact nor any of its market segments carries a policy of its
 * own. Ships closed (Thickness and Drainer board / countertop thickness hidden).
 */
export default function SpecVisibilitySettingsPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Spec Visibility</CardTitle>
      </CardHeader>
      <CardContent>
        <SpecVisibilitySection heading={null} scope={{ kind: 'default' }} />
      </CardContent>
    </Card>
  );
}
