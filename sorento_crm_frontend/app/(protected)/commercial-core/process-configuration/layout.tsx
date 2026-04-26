import type { ReactNode } from 'react';
import { Container } from '@/components/common/container';

export default function ProcessConfigurationLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-[#f9fafb]">
      <Container className="pb-16 pt-8">{children}</Container>
    </div>
  );
}
