'use client';

import { ReactNode } from 'react';
import Link from 'next/link';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Package,
  Users,
  Bot,
  FileText,
  ShoppingCart,
  AlertCircle,
  BarChart3,
  Link2,
  ClipboardList,
} from 'lucide-react';

interface QuickLinkItem {
  href: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}

const quickLinks: QuickLinkItem[] = [
  { href: '/', label: 'Dashboard', description: 'Overview', icon: BarChart3 },
  { href: '/order-management/orders', label: 'Orders', description: 'Order management', icon: ShoppingCart },
  { href: '/master-data-management/products', label: 'Products', description: 'Product catalog', icon: Package },
  { href: '/user-management/contacts', label: 'Internal Users', description: 'Respond contacts', icon: Users },
  { href: '/user-management/access-agents', label: 'AI Agents', description: 'Access agents', icon: Bot },
  { href: '/user-management/permissions', label: 'Permissions', description: 'User permissions', icon: FileText },
  { href: '/user-management/roles', label: 'Roles', description: 'User roles', icon: Users },
  { href: '/complaint-management/complaints', label: 'Complaints', description: 'Complaint management', icon: AlertCircle },
  { href: '/integration-management/integration-logs', label: 'Integration Logs', description: 'API & webhook logs', icon: ClipboardList },
  { href: '/resource-management/smart-linkage', label: 'Smart Linkage', description: 'Attachment linkage', icon: Link2 },
];

export function AppsDropdownMenu({ trigger }: { trigger: ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent className="w-[320px] p-0" side="bottom" align="end">
        <div className="text-xs text-secondary-foreground font-medium px-5 py-3 border-b border-b-border">
          Quick links
        </div>
        <div className="flex flex-col scrollable-y-auto max-h-[400px] divide-y divide-border">
          {quickLinks.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 px-5 py-3 hover:bg-accent/50 transition-colors"
              >
                <div className="flex items-center justify-center shrink-0 rounded-lg bg-accent/60 border border-border size-10">
                  <Icon className="size-5 text-muted-foreground" />
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="text-sm font-medium truncate">{item.label}</span>
                  <span className="text-xs text-muted-foreground truncate">{item.description}</span>
                </div>
              </Link>
            );
          })}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
