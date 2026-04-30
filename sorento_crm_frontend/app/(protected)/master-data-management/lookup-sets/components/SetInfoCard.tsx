'use client';
import { useState } from 'react';
import { Pencil } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import LookupSetFormDialog from './LookupSetFormDialog';
import type { LookupSet } from '../types/lookup.types';

export default function SetInfoCard({ set }: { set: LookupSet }) {
  const [editing, setEditing] = useState(false);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Set info</CardTitle>
        <Button variant="outline" size="sm" onClick={() => setEditing(true)}><Pencil className="size-4" /> Edit</Button>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <div><span className="text-muted-foreground">Key:</span> <span className="font-mono">{set.set_key}</span></div>
        <div><span className="text-muted-foreground">Active:</span> {set.is_active ? 'Yes' : 'No'}</div>
        {set.description && <div className="text-muted-foreground">{set.description}</div>}
      </CardContent>
      <LookupSetFormDialog open={editing} onOpenChange={setEditing} setId={set.id} />
    </Card>
  );
}
