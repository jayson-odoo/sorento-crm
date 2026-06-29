'use client';

import Link from 'next/link';
import { Container } from '@/components/common/container';

export function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="footer">
      <Container>
        <div className="flex flex-col md:flex-row justify-center md:justify-between items-center gap-3 py-5">
          <div className="flex order-2 md:order-1 gap-2 font-normal text-sm">
            <span className="text-muted-foreground">{currentYear} @ Foundryx</span>
          </div>
          <nav className="flex order-1 md:order-2 gap-4 font-normal text-sm text-muted-foreground">
            <Link
              href="/ticket-management/tickets"
              className="hover:text-primary"
            >
              Support
            </Link>
          </nav>
        </div>
      </Container>
    </footer>
  );
}
