'use client';

import { useLookupOptionsByBinding } from '@/hooks/useLookupOptionsByBinding';

export interface LookupBoundLabelProps {
  table: string;
  column: string;
  value: string | null | undefined;
  fallback?: string;
}

export default function LookupBoundLabel({
  table,
  column,
  value,
  fallback = '-',
}: LookupBoundLabelProps) {
  const { data, isLoading } = useLookupOptionsByBinding(table, column);
  const code = (value ?? '').trim();
  if (!code) return <>{fallback}</>;
  if (isLoading || !data) return <>{code}</>;
  const match = data.options.find((o) => o.value.toLowerCase() === code.toLowerCase());
  return <>{match?.label ?? code}</>;
}
