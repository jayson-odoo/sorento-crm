'use client';
import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { useLookupSet } from '../hooks/useLookupSets';
import SetInfoCard from '../components/SetInfoCard';
import OptionsSection from '../components/OptionsSection';
import BindingsSection from '../components/BindingsSection';
import TestResolveCard from '../components/TestResolveCard';

export default function LookupSetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: set, isLoading } = useLookupSet(id);
  if (isLoading) return <Container><SectionSkeleton rows={6} className="py-6" /></Container>;
  if (!set) return <Container>Not found.</Container>;
  return (
    <>
      <Container>
        <PageHeader title={set.name} />
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
