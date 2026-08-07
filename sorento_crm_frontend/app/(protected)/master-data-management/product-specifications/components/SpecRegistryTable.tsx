'use client';

import { Fragment, useEffect, useState } from 'react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { getSpecRegistry } from '../services/productSpecService';
import type { SpecRegistryKey } from '../types/productSpec.types';
import SpecKeyEditor from './SpecKeyEditor';

/**
 * Every spec key the system knows, and every word that resolves onto it.
 *
 * This IS the extraction prompt the n8n parser reads and the vocabulary the ranker's
 * word-resolver matches against — not a description of it. If a phrase isn't reaching
 * a product, this table says whether the word simply isn't bound to anything yet.
 */
export default function SpecRegistryTable() {
  const [keys, setKeys] = useState<SpecRegistryKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  useEffect(() => {
    getSpecRegistry()
      .then((r) => setKeys(r.keys))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  const allSynonyms = (key: SpecRegistryKey): string[] => {
    if (key.data_type === 'boolean') {
      return key.synonyms?.true ?? [];
    }
    return Object.values(key.synonyms ?? {}).flat();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Spec keys supported ({keys.length})</CardTitle>
      </CardHeader>
      <CardContent>
        {error && (
          <Alert variant="destructive">
            <AlertIcon />
            <AlertTitle>{error}</AlertTitle>
          </Alert>
        )}

        {loading && (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        )}

        {!loading && !error && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="pb-2 pr-4">Key</th>
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Applies to</th>
                  <th className="pb-2 pr-4">Weight</th>
                  <th className="pb-2 pr-4">Seen in</th>
                  <th className="pb-2 pr-4">Words that resolve to it</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => {
                  const gate = Object.entries(key.applies_when ?? {});
                  const synonyms = allSynonyms(key);
                  return (
                    <Fragment key={key.spec_key}>
                    <tr className="border-b last:border-0 align-top">
                      <td className="py-2 pr-4 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{key.label}</span>
                          {!key.is_active && (
                            <Badge variant="secondary" size="sm">
                              Off
                            </Badge>
                          )}
                          {key.source === 'user' && (
                            <Badge variant="primary" size="sm">
                              Yours
                            </Badge>
                          )}
                        </div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {key.spec_key}
                        </div>
                      </td>
                      <td className="py-2 pr-4 whitespace-nowrap text-muted-foreground">
                        {key.data_type}
                        {key.unit ? ` (${key.unit})` : ''}
                      </td>
                      <td className="py-2 pr-4 whitespace-nowrap text-muted-foreground">
                        {gate.length > 0
                          ? gate.map(([, values]) => values.join(', ')).join('; ')
                          : 'Every class'}
                      </td>
                      <td className="py-2 pr-4 tabular-nums text-muted-foreground">
                        {key.rank_weight ?? '-'}
                      </td>
                      <td className="py-2 pr-4 tabular-nums text-muted-foreground">
                        {key.measured_coverage != null
                          ? key.measured_coverage.toLocaleString()
                          : '-'}
                      </td>
                      <td className="py-2 pr-4">
                        {synonyms.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {synonyms.map((word) => (
                              <Badge key={word} variant="outline" size="sm">
                                {word}
                              </Badge>
                            ))}
                          </div>
                        ) : key.allowed_values.length > 0 ? (
                          <span className="text-muted-foreground">
                            {key.allowed_values.join(', ')}
                            <span className="italic"> (no synonyms bound yet)</span>
                          </span>
                        ) : (
                          <span className="text-muted-foreground italic">
                            open vocabulary, sourced from the catalog
                          </span>
                        )}
                      </td>
                      <td className="py-2 whitespace-nowrap">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            setEditing(editing === key.spec_key ? null : key.spec_key)
                          }
                        >
                          {editing === key.spec_key ? 'Close' : 'Edit'}
                        </Button>
                      </td>
                    </tr>
                    {editing === key.spec_key && (
                      <tr className="border-b bg-muted/10">
                        <td colSpan={7} className="p-3">
                          <SpecKeyEditor
                            specKey={key}
                            onCancel={() => setEditing(null)}
                            onSaved={(updated) => {
                              setKeys((current) =>
                                current.map((k) =>
                                  k.spec_key === updated.spec_key ? updated : k,
                                ),
                              );
                              setEditing(null);
                            }}
                          />
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
