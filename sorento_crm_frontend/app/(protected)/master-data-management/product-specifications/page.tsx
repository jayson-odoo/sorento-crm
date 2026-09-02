'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown, MessageSquareText, Plus, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { useHasPermission } from '@/hooks/usePermissions';
import { AddSpecificationDialog } from './components/AddSpecificationDialog';
import { SpecRegistryPage } from './components/SpecRegistryPage';
import { TryPhraseDialog } from './components/TryPhraseDialog';
import { useSpecRegistryMutations } from './hooks/useSpecRegistryMutations';

export default function ProductSpecificationsPage() {
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [trying, setTrying] = useState(false);
  const canAdd = useHasPermission('master_data.spec_registry.add');
  const canEdit = useHasPermission('master_data.spec_registry.edit');
  const { reread } = useSpecRegistryMutations();

  return (
    <>
      <Container>
        <PageHeader
          title="Product Specifications"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline">
                    Actions
                    <ChevronDown className="size-3.5 opacity-60" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => setTrying(true)}>
                    <MessageSquareText className="size-4" aria-hidden />
                    Try a phrase
                  </DropdownMenuItem>
                  {canEdit && (
                    <DropdownMenuItem
                      disabled={reread.isPending}
                      onSelect={() => reread.mutate()}
                    >
                      <RefreshCw className="size-4" aria-hidden />
                      Reread catalogue
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
              {canAdd && (
                <Button onClick={() => setAdding(true)}>
                  <Plus className="size-4" aria-hidden />
                  Add specification
                </Button>
              )}
            </div>
          }
        />
      </Container>

      <Container>
        <SpecRegistryPage />
      </Container>

      <AddSpecificationDialog
        open={adding}
        onOpenChange={setAdding}
        onCreated={(specKey) =>
          router.push(`/master-data-management/product-specifications/${specKey}`)
        }
      />
      <TryPhraseDialog open={trying} onOpenChange={setTrying} />
    </>
  );
}
