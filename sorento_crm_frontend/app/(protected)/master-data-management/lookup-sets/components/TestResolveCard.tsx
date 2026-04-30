'use client';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useResolve } from '../hooks/useLookupSets';
import type { LookupResolveResponse } from '../types/lookup.types';

export default function TestResolveCard({ setKey }: { setKey: string }) {
  const [raw, setRaw] = useState('');
  const [result, setResult] = useState<LookupResolveResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const m = useResolve();

  async function go() {
    setErr(null); setResult(null);
    try {
      const r = await m.mutateAsync({ set_key: setKey, raw });
      setResult(r);
    } catch (e: any) { setErr(e.message || 'Unresolved'); }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Test resolve</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="text-sm text-muted-foreground">
          Try a raw keyword and see how the backend resolves it for n8n.
        </div>
        <div className="flex gap-2">
          <Input value={raw} onChange={(e) => setRaw(e.target.value)} placeholder="e.g. urgent now" />
          <Button onClick={go} disabled={!raw}>Resolve</Button>
        </div>
        {result && (
          <div className="text-sm font-mono bg-muted rounded-md p-2">
            value=<b>{result.value}</b> · label={result.label} ·
            match_type={result.match_type} · score={result.score.toFixed(2)}
            {result.matched_keyword ? <> · keyword=<i>{result.matched_keyword}</i></> : null}
          </div>
        )}
        {err && <div className="text-sm text-destructive">{err}</div>}
      </CardContent>
    </Card>
  );
}
