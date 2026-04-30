'use client';
import { use } from 'react';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import { useLookupSet } from '../hooks/useLookupSets';
import SetInfoCard from '../components/SetInfoCard';
import OptionsSection from '../components/OptionsSection';
import BindingsSection from '../components/BindingsSection';
import TestResolveCard from '../components/TestResolveCard';

export default function LookupSetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: set, isLoading } = useLookupSet(id);
  if (isLoading) return <Container>Loading…</Container>;
  if (!set) return <Container>Not found.</Container>;
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>{set.name}</ToolbarTitle>
          </ToolbarHeading>
        </Toolbar>
      </Container>
      <Container className="space-y-6">
        <SetInfoCard set={set} />
        <OptionsSection setId={id} />
        <BindingsSection setId={id} />
        <TestResolveCard setKey={set.set_key} />
      </Container>
    </>
  );
}
