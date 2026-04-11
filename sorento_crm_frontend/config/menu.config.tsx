import {
  AlertCircle,
  Award,
  Badge,
  Bell,
  Bitcoin,
  Bolt,
  Book,
  Briefcase,
  Building,
  CalendarCheck,
  Captions,
  CheckCircle,
  Clock,
  Code,
  Codepen,
  Coffee,
  File as DocumentIcon,
  Euro,
  Eye,
  File,
  FileQuestion,
  FileText,
  Flag,
  Folder,
  Ghost,
  Gift,
  GitBranch,
  Grid,
  Heart,
  HelpCircle,
  Kanban,
  Key,
  Layout,
  LayoutGrid,
  LifeBuoy,
  Megaphone,
  MessageSquare,
  Monitor,
  Network,
  Package,
  Users as PeopleIcon,
  Plug,
  ScrollText,
  Settings,
  Share2,
  Shield,
  ShieldUser,
  ShoppingBag,
  ShoppingCart,
  SquareMousePointer,
  Star,
  Theater,
  TrendingUp,
  Truck,
  UserCheck,
  UserCircle,
  Users,
  Warehouse,
  Briefcase as WorkIcon,
  Zap,
} from 'lucide-react';
import { type MenuConfig } from './types';

export const MENU_SIDEBAR: MenuConfig = [
  {
    title: 'Dashboards',
    icon: LayoutGrid,
    children: [
      { title: 'Light Sidebar', path: '/' },
    ],
  },
  { heading: 'User' },
  // Hidden: Public Profile
  // {
  //   title: 'Public Profile',
  //   icon: UserCircle,
  //   children: [
  //     {
  //       title: 'Profiles',
  //       children: [
  //         { title: 'Default', path: '/public-profile/profiles/default' },
  //         { title: 'Creator', path: '/public-profile/profiles/creator' },
  //         { title: 'Company', path: '/public-profile/profiles/company' },
  //         { title: 'NFT', path: '/public-profile/profiles/nft' },
  //         { title: 'Blogger', path: '/public-profile/profiles/blogger' },
  //         { title: 'CRM', path: '/public-profile/profiles/crm' },
  //         {
  //           title: 'More',
  //           collapse: true,
  //           collapseTitle: 'Show less',
  //           expandTitle: 'Show 4 more',
  //           children: [
  //             { title: 'Gamer', path: '/public-profile/profiles/gamer' },
  //             { title: 'Feeds', path: '/public-profile/profiles/feeds' },
  //             { title: 'Plain', path: '/public-profile/profiles/plain' },
  //             { title: 'Modal', path: '/public-profile/profiles/modal' },
  //           ],
  //         },
  //       ],
  //     },
  //     {
  //       title: 'Projects',
  //       children: [
  //         { title: '3 Columns', path: '/public-profile/projects/3-columns' },
  //         { title: '2 Columns', path: '/public-profile/projects/2-columns' },
  //       ],
  //     },
  //     { title: 'Works', path: '/public-profile/works' },
  //     { title: 'Teams', path: '/public-profile/teams' },
  //     { title: 'Network', path: '/public-profile/network' },
  //     { title: 'Activity', path: '/public-profile/activity' },
  //     {
  //       title: 'More',
  //       collapse: true,
  //       collapseTitle: 'Show less',
  //       expandTitle: 'Show 3 more',
  //       children: [
  //         { title: 'Campaigns - Card', path: '/public-profile/campaigns/card' },
  //         { title: 'Campaigns - List', path: '/public-profile/campaigns/list' },
  //         { title: 'Empty', path: '/public-profile/empty' },
  //       ],
  //     },
  //   ],
  // },
  // Hidden: My Account
  // {
  //   title: 'My Account',
  //   icon: Settings,
  //   children: [
  //     {
  //       title: 'Account',
  //       children: [
  //         { title: 'Get Started', path: '/account/home/get-started' },
  //         { title: 'User Profile', path: '/user-management/account' },
  //         { title: 'Company Profile', path: '/account/home/company-profile' },
  //         {
  //           title: 'Settings - With Sidebar',
  //           path: '/account/home/settings-sidebar',
  //         },
  //         {
  //           title: 'Settings - Enterprise',
  //           path: '/account/home/settings-enterprise',
  //         },
  //         { title: 'Settings - Plain', path: '/account/home/settings-plain' },
  //         { title: 'Settings - Modal', path: '/account/home/settings-modal' },
  //       ],
  //     },
  //     {
  //       title: 'Billing',
  //       children: [
  //         { title: 'Billing - Basic', path: '/account/billing/basic' },
  //         {
  //           title: 'Billing - Enterprise',
  //           path: '/account/billing/enterprise',
  //         },
  //         { title: 'Plans', path: '/account/billing/plans' },
  //         { title: 'Billing History', path: '/account/billing/history' },
  //       ],
  //     },
  //     {
  //       title: 'Security',
  //       children: [
  //         { title: 'Get Started', path: '/account/security/get-started' },
  //         { title: 'Security Overview', path: '/account/security/overview' },
  //         {
  //           title: 'Allowed IP Addresses',
  //           path: '/account/security/allowed-ip-addresses',
  //         },
  //         {
  //           title: 'Privacy Settings',
  //           path: '/account/security/privacy-settings',
  //         },
  //         {
  //           title: 'Device Management',
  //           path: '/account/security/device-management',
  //         },
  //         {
  //           title: 'Backup & Recovery',
  //           path: '/account/security/backup-and-recovery',
  //         },
  //         {
  //           title: 'Current Sessions',
  //           path: '/account/security/current-sessions',
  //         },
  //         { title: 'Security Log', path: '/account/security/security-log' },
  //       ],
  //     },
  //     {
  //       title: 'Members & Roles',
  //       children: [
  //         { title: 'Teams Starter', path: '/account/members/team-starter' },
  //         { title: 'Teams', path: '/account/members/teams' },
  //         { title: 'Team Info', path: '/account/members/team-info' },
  //         {
  //           title: 'Members Starter',
  //           path: '/account/members/members-starter',
  //         },
  //         { title: 'Team Members', path: '/account/members/team-members' },
  //         { title: 'Import Members', path: '/account/members/import-members' },
  //         { title: 'Roles', path: '/account/members/roles' },
  //         {
  //           title: 'Permissions - Toggler',
  //           path: '/account/members/permissions-toggle',
  //         },
  //         {
  //           title: 'Permissions - Check',
  //           path: '/account/members/permissions-check',
  //         },
  //       ],
  //     },
  //     { title: 'Integrations', path: '/account/integrations' },
  //     { title: 'Notifications', path: '/account/notifications' },
  //     { title: 'API Keys', path: '/account/api-keys' },
  //     {
  //       title: 'More',
  //       collapse: true,
  //       collapseTitle: 'Show less',
  //       expandTitle: 'Show 3 more',
  //       children: [
  //         { title: 'Appearance', path: '/account/appearance' },
  //         { title: 'Invite a Friend', path: '/account/invite-a-friend' },
  //         { title: 'Activity', path: '/account/activity' },
  //       ],
  //     },
  //   ],
  // },
  // Hidden: Network
  // {
  //   title: 'Network',
  //   icon: Users,
  //   children: [
  //     { title: 'Get Started', path: '/network/get-started' },
  //     {
  //       title: 'User Cards',
  //       children: [
  //         { title: 'Mini Cards', path: '/network/user-cards/mini-cards' },
  //         { title: 'Team Crew', path: '/network/user-cards/team-crew' },
  //         { title: 'Author', path: '/network/user-cards/author' },
  //         { title: 'NFT', path: '/network/user-cards/nft' },
  //         { title: 'Social', path: '/network/user-cards/social' },
  //       ],
  //     },
  //     {
  //       title: 'User Table',
  //       children: [
  //         { title: 'Team Crew', path: '/network/user-table/team-crew' },
  //         { title: 'App Roster', path: '/network/user-table/app-roster' },
  //         {
  //           title: 'Market Authors',
  //           path: '/network/user-table/market-authors',
  //         },
  //         { title: 'SaaS Users', path: '/network/user-table/saas-users' },
  //         { title: 'Store Clients', path: '/network/user-table/store-clients' },
  //         { title: 'Visitors', path: '/network/user-table/visitors' },
  //       ],
  //     },
  //     { title: 'Cooperations', path: '/network/cooperations', disabled: true },
  //     { title: 'Leads', path: '/network/leads', disabled: true },
  //     { title: 'Donators', path: '/network/donators', disabled: true },
  //   ],
  // },
  // Hidden: Authentication
  // {
  //   title: 'Authentication',
  //   icon: Shield,
  //   children: [
  //     {
  //       title: 'Sign In',
  //       path: '/signin',
  //     },
  //     {
  //       title: 'Check Email',
  //       path: '/signup',
  //     },
  //     {
  //       title: 'Reset Password',
  //       path: '/reset-password',
  //     },
  //     {
  //       title: '2FA',
  //       path: '/2fa',
  //     },
  //     { title: 'Welcome Message', path: '/auth/welcome-message' },
  //     { title: 'Account Deactivated', path: '/auth/account-deactivated' },
  //     { title: 'Error 404', path: '/error/404' },
  //     { title: 'Error 500', path: '/error/500' },
  //   ],
  // },
  { heading: 'Apps' },
  {
    title: 'User Management',
    icon: ShieldUser,
    moduleKey: 'base',
    children: [
      {
        title: 'Administrative Users',
        path: '/user-management/users',
        permission: 'user_management.users.view',
      },
      {
        title: 'Roles',
        path: '/user-management/roles',
        permission: 'user_management.roles.view',
      },
      {
        title: 'Permissions',
        path: '/user-management/permissions',
        permission: 'user_management.permissions.view',
      },
      {
        title: 'AI Agents',
        path: '/user-management/access-agents',
        permission: 'user_management.access_agents.view',
      },
      {
        title: 'Teams',
        path: '/user-management/teams',
        permission: 'user_management.teams.view',
      },
      {
        title: 'Internal Users',
        path: '/user-management/contact-access-agents',
      },
      {
        title: 'Contact Access Types',
        path: '/user-management/contact-access-types',
      },
      {
        title: 'Account',
        path: '/user-management/account',
        permission: 'user_management.account.view',
      },
      {
        title: 'Logs',
        path: '/user-management/logs',
        permission: 'user_management.logs.view',
      },
      {
        title: 'Settings',
        path: '/user-management/settings',
        permission: 'user_management.settings.view',
      },
    ],
  },
  {
    title: 'Order Management',
    icon: ShoppingCart,
    moduleKey: 'order',
    children: [
      {
        title: 'Orders',
        path: '/order-management/orders',
        permission: 'order_management.orders.view',
      },
      {
        title: 'Order Status',
        path: '/order-management/order-statuses',
        permission: 'order_management.order_statuses.view',
      },
      {
        title: 'Customers',
        path: '/order-management/customers',
        permission: 'order_management.customers.view',
      },
    ],
  },
  {
    title: 'Complaint Management',
    icon: AlertCircle,
    moduleKey: 'complaints',
    children: [
      {
        title: 'Complaints',
        path: '/complaint-management/complaints',
      },
    ],
  },
  {
    title: 'SLA Management',
    icon: Clock,
    moduleKey: 'sla',
    children: [
      {
        title: 'SLA Policies',
        path: '/sla-management/sla-policies',
      },
      {
        title: 'Conversation SLA Tracking',
        path: '/sla-management/conversation-sla-tracking',
      },
      {
        title: 'SLA Event Logs',
        path: '/sla-management/escalation-logs',
      },
    ],
  },
  {
    title: 'Product Management',
    icon: Package,
    moduleKey: 'product',
    children: [
    {
      title: 'Products',
      children: [
        {
          title: 'All Products',
          path: '/master-data-management/products',
          permission: 'master_data.products.view',
        },
        {
          title: 'Product Attachments',
          path: '/master-data-management/product-attachments',
          permission: 'master_data.product_attachments.view',
        },
      ],
    },
    {
      title: 'Product Categories',
      path: '/master-data-management/product-categories',
      permission: 'master_data.product_categories.view',
    },
    {
      title: 'Brands',
      path: '/master-data-management/brands',
      permission: 'master_data.brands.view',
    },
    {
      title: 'Units of Measure',
      path: '/master-data-management/units-of-measure',
      permission: 'master_data.units_of_measure.view',
    },
    ],
  },
  {
    title: 'Procurement',
    icon: ShoppingBag,
    moduleKey: 'procurement',
    children: [
      {
        title: 'Suppliers',
        path: '/procurement-management/suppliers',
        permission: 'procurement.suppliers.view',
      },
      {
        title: 'Product-Suppliers',
        path: '/procurement-management/product-suppliers',
        permission: 'procurement.product_suppliers.view',
      },
      {
        title: 'Packing Lists',
        path: '/procurement-management/packing-lists',
        permission: 'procurement.packing_lists.view',
      },
      {
        title: 'SPO Allocations',
        path: '/procurement-management/spo-allocations',
        permission: 'procurement.spo_allocations.view',
      },
      {
        title: 'GRN',
        path: '/procurement-management/grn',
        permission: 'procurement.grn.view',
      },
      {
        title: 'Picking Lines',
        path: '/procurement-management/picking-lines',
        permission: 'procurement.picking_lines.view',
      },
      {
        title: 'Stock Inquiries',
        path: '/procurement-management/stock-inquiries',
        permission: 'procurement.stock_inquiries.view',
      },
      {
        title: 'Purchase Requests',
        path: '/procurement-management/purchase-requests',
        permission: 'procurement.purchase_requests.view',
      },
      {
        title: 'Sponsorship Forms',
        path: '/procurement-management/sponsorship-forms',
        permission: 'procurement.sponsorship_forms.view',
      },
    ],
  },
  {
    title: 'Inventory Management',
    icon: Warehouse,
    moduleKey: 'inventory',
    children: [
      {
        title: 'Warehouses',
        path: '/inventory-management/warehouses',
        permission: 'inventory.warehouses.view',
      },
      {
        title: 'Storage Zones',
        path: '/inventory-management/storage-zones',
        permission: 'inventory.storage_zones.view',
      },
      {
        title: 'Stock',
        path: '/inventory-management/stock',
        permission: 'inventory.stock.view',
      },
      {
        title: 'Stock Batches',
        path: '/inventory-management/stock-batches',
        permission: 'inventory.stock_batches.view',
      },
      {
        title: 'Stock Ledger',
        path: '/inventory-management/stock-ledger',
        permission: 'inventory.stock_ledger.view',
      },
    ],
  },
  {
    title: 'Marketing Management',
    icon: Megaphone,
    moduleKey: 'marketing',
    children: [
      {
        title: 'Promotions',
        children: [
          {
            title: 'All Promotions',
            path: '/marketing-management/promotions',
          },
          {
            title: 'Promotion Attachments',
            path: '/marketing-management/promotion-attachments',
          },
        ],
      },
      {
        title: 'Promotion Products',
        path: '/marketing-management/promotion-products',
      },
      {
        title: 'Campaigns',
        path: '/marketing-management/campaigns',
      },
    ],
  },
  {
    title: 'Forms Management',
    icon: FileText,
    moduleKey: 'forms',
    children: [
      {
        title: 'Forms',
        path: '/forms-management/forms',
      },
    ],
  },
  {
    title: 'Workflow Forms',
    icon: GitBranch,
    moduleKey: 'workflow_forms',
    children: [
      {
        title: 'Definitions',
        path: '/workflow-forms-management/definitions',
        permission: 'workflow_forms.definitions.view',
      },
    ],
  },
  {
    title: 'Resource Management',
    icon: Folder,
    moduleKey: 'resources',
    children: [
      {
        title: 'Files',
        path: '/resource-management/attachment-directories',
      },
      {
        title: 'Trash',
        path: '/resource-management/trash',
      },
      {
        title: 'Attachment Types',
        path: '/resource-management/attachment-types',
      },
    ],
  },
  {
    title: 'System Management',
    icon: Settings,
    moduleKey: 'base',
    children: [
      {
        title: 'App Store',
        path: '/system-management/app-store',
        permission: 'system.modules.manage',
      },
      {
        title: 'Module bundles',
        path: '/system-management/app-store/bundles',
        permission: 'system.modules.manage',
      },
      {
        title: 'Import Jobs',
        path: '/system-management/import-jobs',
      },
      {
        title: 'Import Logs',
        path: '/system-management/import-logs',
      },
      {
        title: 'Integration Logs',
        path: '/integration-management/integration-logs',
      },
      {
        title: 'Scheduled Tasks',
        path: '/system-management/scheduled-tasks',
      },
      {
        title: 'Outgoing Mails',
        path: '/system-management/outgoing-mails',
        permission: 'system.outgoing_mails.view',
      },
      {
        title: 'Work Calendar',
        path: '/system-management/work-calendar',
      },
      {
        title: 'Running Numbers',
        path: '/system-management/numbering-rules',
      },
    ],
  },
  // Hidden: Store - Client
  // {
  //   title: 'Store - Client',
  //   icon: Users,
  //   children: [
  //     { title: 'Home', path: '/store-client/home' },
  //     {
  //       title: 'Search Results - Grid',
  //       path: '/store-client/search-results-grid',
  //     },
  //     {
  //       title: 'Search Results - List',
  //       path: '/store-client/search-results-list',
  //     },
  //     { title: 'Product Details', path: '/store-client/product-details' },
  //     { title: 'Wishlist', path: '/store-client/wishlist' },
  //     {
  //       title: 'Checkout',
  //       children: [
  //         {
  //           title: 'Order Summary',
  //           path: '/store-client/checkout/order-summary',
  //         },
  //         {
  //           title: 'Shipping Info',
  //           path: '/store-client/checkout/shipping-info',
  //         },
  //         {
  //           title: 'Payment Method',
  //           path: '/store-client/checkout/payment-method',
  //         },
  //         {
  //           title: 'Order Placed',
  //           path: '/store-client/checkout/order-placed',
  //         },
  //       ],
  //     },
  //     { title: 'My Orders', path: '/store-client/my-orders' },
  //     { title: 'Order Receipt', path: '/store-client/order-receipt' },
  //   ],
  // },
  // Hidden: Store - Admin
  // {
  //   title: 'Store - Admin',
  //   icon: Bolt,
  //   disabled: true,
  //   children: [
  //     { title: 'Dashboard', path: '/store-admin/dashboard' },
  //     {
  //       title: 'Inventory',
  //       children: [
  //         {
  //           title: 'All Products',
  //           path: '/store-admin/inventory/all-products',
  //         },
  //         {
  //           title: 'Current Stock',
  //           path: '/store-admin/inventory/current-stock',
  //         },
  //         {
  //           title: 'Inbound Stock',
  //           path: '/store-admin/inventory/inbound-stock',
  //         },
  //         {
  //           title: 'Outbound Stock',
  //           path: '/store-admin/inventory/outbound-stock',
  //         },
  //         {
  //           title: 'Stock Planner',
  //           path: '/store-admin/inventory/stock-planner',
  //         },
  //         { title: 'Track Shipping', path: '/' },
  //         { title: 'Create Shipping Label', path: '/' },
  //       ],
  //     },
  //   ],
  // },
  // Hidden: Store - Services, AI Promt, Invoice Generator
  // { title: 'Store - Services', icon: Codepen, disabled: true },
  // { title: 'AI Promt', icon: Theater, disabled: true },
  // { title: 'Invoice Generator', icon: ScrollText, disabled: true },
];

export const MENU_SIDEBAR_CUSTOM: MenuConfig = [
  {
    title: 'Store - Client',
    icon: Users,
    children: [
      { title: 'Home', path: '/store-client/home' },
      {
        title: 'Search Results',
        children: [
          {
            title: 'Search Results - Grid',
            path: '/store-client/search-results-grid',
          },
          {
            title: 'Search Results - List',
            path: '/store-client/search-results-list',
          },
        ],
      },
      {
        title: 'Overlays',
        children: [
          { title: 'Product Details', path: '/store-client/product-details' },
          { title: 'Wishlist', path: '/store-client/wishlist' },
        ],
      },
      {
        title: 'Checkout',
        children: [
          {
            title: 'Order Summary',
            path: '/store-client/checkout/order-summary',
          },
          {
            title: 'Shipping Info',
            path: '/store-client/checkout/shipping-info',
          },
          {
            title: 'Payment Method',
            path: '/store-client/checkout/payment-method',
          },
          {
            title: 'Order Placed',
            path: '/store-client/checkout/order-placed',
          },
        ],
      },
      { title: 'My Orders', path: '/store-client/my-orders' },
      { title: 'Order Receipt', path: '/store-client/order-receipt' },
    ],
  },
];

export const MENU_SIDEBAR_COMPACT: MenuConfig = [
  {
    title: 'Dashboards',
    icon: LayoutGrid,
    path: '/',
  },
  {
    title: 'Public Profile',
    icon: UserCircle,
    children: [
      {
        title: 'Profiles',
        children: [
          { title: 'Default', path: '/public-profile/profiles/default' },
          { title: 'Creator', path: '/public-profile/profiles/creator' },
          { title: 'Company', path: '/public-profile/profiles/company' },
          { title: 'NFT', path: '/public-profile/profiles/nft' },
          { title: 'Blogger', path: '/public-profile/profiles/blogger' },
          { title: 'CRM', path: '/public-profile/profiles/crm' },
          {
            title: 'More',
            collapse: true,
            collapseTitle: 'Show less',
            expandTitle: 'Show 4 more',
            children: [
              { title: 'Gamer', path: '/public-profile/profiles/gamer' },
              { title: 'Feeds', path: '/public-profile/profiles/feeds' },
              { title: 'Plain', path: '/public-profile/profiles/plain' },
              { title: 'Modal', path: '/public-profile/profiles/modal' },
            ],
          },
        ],
      },
      {
        title: 'Projects',
        children: [
          { title: '3 Columns', path: '/public-profile/projects/3-columns' },
          { title: '2 Columns', path: '/public-profile/projects/2-columns' },
        ],
      },
      { title: 'Works', path: '/public-profile/works' },
      { title: 'Teams', path: '/public-profile/teams' },
      { title: 'Network', path: '/public-profile/network' },
      { title: 'Activity', path: '/public-profile/activity' },
      {
        title: 'More',
        collapse: true,
        collapseTitle: 'Show less',
        expandTitle: 'Show 3 more',
        children: [
          { title: 'Campaigns - Card', path: '/public-profile/campaigns/card' },
          { title: 'Campaigns - List', path: '/public-profile/campaigns/list' },
          { title: 'Empty', path: '/public-profile/empty' },
        ],
      },
    ],
  },
  {
    title: 'My Account',
    icon: Settings,
    children: [
      {
        title: 'Account',
        children: [
          { title: 'Get Started', path: '/account/home/get-started' },
          { title: 'User Profile', path: '/user-management/account' },
          { title: 'Company Profile', path: '/account/home/company-profile' },
          {
            title: 'Settings - With Sidebar',
            path: '/account/home/settings-sidebar',
          },
          {
            title: 'Settings - Enterprise',
            path: '/account/home/settings-enterprise',
          },
          { title: 'Settings - Plain', path: '/account/home/settings-plain' },
          { title: 'Settings - Modal', path: '/account/home/settings-modal' },
        ],
      },
      {
        title: 'Billing',
        children: [
          { title: 'Billing - Basic', path: '/account/billing/basic' },
          {
            title: 'Billing - Enterprise',
            path: '/account/billing/enterprise',
          },
          { title: 'Plans', path: '/account/billing/plans' },
          { title: 'Billing History', path: '/account/billing/history' },
        ],
      },
      {
        title: 'Security',
        children: [
          { title: 'Get Started', path: '/account/security/get-started' },
          { title: 'Security Overview', path: '/account/security/overview' },
          {
            title: 'Allowed IP Addresses',
            path: '/account/security/allowed-ip-addresses',
          },
          {
            title: 'Privacy Settings',
            path: '/account/security/privacy-settings',
          },
          {
            title: 'Device Management',
            path: '/account/security/device-management',
          },
          {
            title: 'Backup & Recovery',
            path: '/account/security/backup-and-recovery',
          },
          {
            title: 'Current Sessions',
            path: '/account/security/current-sessions',
          },
          { title: 'Security Log', path: '/account/security/security-log' },
        ],
      },
      {
        title: 'Members & Roles',
        children: [
          { title: 'Teams Starter', path: '/account/members/team-starter' },
          { title: 'Teams', path: '/account/members/teams' },
          { title: 'Team Info', path: '/account/members/team-info' },
          {
            title: 'Members Starter',
            path: '/account/members/members-starter',
          },
          { title: 'Team Members', path: '/account/members/team-members' },
          { title: 'Import Members', path: '/account/members/import-members' },
          { title: 'Roles', path: '/account/members/roles' },
          {
            title: 'Permissions - Toggler',
            path: '/account/members/permissions-toggle',
          },
          {
            title: 'Permissions - Check',
            path: '/account/members/permissions-check',
          },
        ],
      },
      { title: 'Integrations', path: '/account/integrations' },
      { title: 'Notifications', path: '/account/notifications' },
      { title: 'API Keys', path: '/account/api-keys' },
      {
        title: 'More',
        collapse: true,
        collapseTitle: 'Show less',
        expandTitle: 'Show 3 more',
        children: [
          { title: 'Appearance', path: '/account/appearance' },
          { title: 'Invite a Friend', path: '/account/invite-a-friend' },
          { title: 'Activity', path: '/account/activity' },
        ],
      },
    ],
  },
  {
    title: 'Network',
    icon: Users,
    children: [
      { title: 'Get Started', path: '/network/get-started' },
      {
        title: 'User Cards',
        children: [
          { title: 'Mini Cards', path: '/network/user-cards/mini-cards' },
          { title: 'Team Crew', path: '/network/user-cards/team-crew' },
          { title: 'Author', path: '/network/user-cards/author' },
          { title: 'NFT', path: '/network/user-cards/nft' },
          { title: 'Social', path: '/network/user-cards/social' },
        ],
      },
      {
        title: 'User Table',
        children: [
          { title: 'Team Crew', path: '/network/user-table/team-crew' },
          { title: 'App Roster', path: '/network/user-table/app-roster' },
          {
            title: 'Market Authors',
            path: '/network/user-table/market-authors',
          },
          { title: 'SaaS Users', path: '/network/user-table/saas-users' },
          { title: 'Store Clients', path: '/network/user-table/store-clients' },
          { title: 'Visitors', path: '/network/user-table/visitors' },
        ],
      },
      { title: 'Cooperations', path: '/network/cooperations', disabled: true },
      { title: 'Leads', path: '/network/leads', disabled: true },
      { title: 'Donators', path: '/network/donators', disabled: true },
    ],
  },
  {
    title: 'Store - Client',
    icon: ShoppingCart,
    children: [
      { title: 'Home', path: '/store-client/home' },
      {
        title: 'Search Results - Grid',
        path: '/store-client/search-results-grid',
      },
      {
        title: 'Search Results - List',
        path: '/store-client/search-results-list',
      },
      { title: 'Product Details', path: '/store-client/product-details' },
      { title: 'Wishlist', path: '/store-client/wishlist' },
      {
        title: 'Checkout',
        children: [
          {
            title: 'Order Summary',
            path: '/store-client/checkout/order-summary',
          },
          {
            title: 'Shipping Info',
            path: '/store-client/checkout/shipping-info',
          },
          {
            title: 'Payment Method',
            path: '/store-client/checkout/payment-method',
          },
          {
            title: 'Order Placed',
            path: '/store-client/checkout/order-placed',
          },
        ],
      },
      { title: 'My Orders', path: '/store-client/my-orders' },
      { title: 'Order Receipt', path: '/store-client/order-receipt' },
    ],
  },
  {
    title: 'User Management',
    icon: ShieldUser,
    moduleKey: 'base',
    children: [
      {
        title: 'Administrative Users',
        path: '/user-management/users',
      },
      {
        title: 'Roles',
        path: '/user-management/roles',
      },
      {
        title: 'Permissions',
        path: '/user-management/permissions',
      },
      {
        title: 'AI Agents',
        path: '/user-management/access-agents',
      },
      {
        title: 'Teams',
        path: '/user-management/teams',
      },
      {
        title: 'Internal Users',
        path: '/user-management/contact-access-agents',
      },
      {
        title: 'Contact Access Types',
        path: '/user-management/contact-access-types',
      },
      {
        title: 'Account',
        path: '/user-management/account',
      },
      {
        title: 'Logs',
        path: '/user-management/logs',
      },
      {
        title: 'Settings',
        path: '/user-management/settings',
      },
    ],
  },
  {
    title: 'Order Management',
    icon: ShoppingCart,
    moduleKey: 'order',
    children: [
      {
        title: 'Orders',
        path: '/order-management/orders',
      },
      {
        title: 'Order Status',
        path: '/order-management/order-statuses',
      },
      {
        title: 'Customers',
        path: '/order-management/customers',
      },
    ],
  },
  {
    title: 'Complaint Management',
    icon: AlertCircle,
    moduleKey: 'complaints',
    children: [
      {
        title: 'Complaints',
        path: '/complaint-management/complaints',
      },
    ],
  },
  {
    title: 'SLA Management',
    icon: Clock,
    moduleKey: 'sla',
    children: [
      {
        title: 'SLA Policies',
        path: '/sla-management/sla-policies',
      },
      {
        title: 'Conversation SLA Tracking',
        path: '/sla-management/conversation-sla-tracking',
      },
      {
        title: 'SLA Event Logs',
        path: '/sla-management/escalation-logs',
      },
    ],
  },
  {
    title: 'Product Management',
    icon: Package,
    moduleKey: 'product',
    children: [
    {
      title: 'Products',
      children: [
        {
          title: 'All Products',
          path: '/master-data-management/products',
          permission: 'master_data.products.view',
        },
        {
          title: 'Product Attachments',
          path: '/master-data-management/product-attachments',
          permission: 'master_data.product_attachments.view',
        },
      ],
    },
    {
      title: 'Product Categories',
      path: '/master-data-management/product-categories',
      permission: 'master_data.product_categories.view',
    },
    {
      title: 'Brands',
      path: '/master-data-management/brands',
      permission: 'master_data.brands.view',
    },
    {
      title: 'Units of Measure',
      path: '/master-data-management/units-of-measure',
      permission: 'master_data.units_of_measure.view',
    },
    ],
  },
  {
    title: 'Procurement',
    icon: ShoppingBag,
    moduleKey: 'procurement',
    children: [
      {
        title: 'Suppliers',
        path: '/procurement-management/suppliers',
        permission: 'procurement.suppliers.view',
      },
      {
        title: 'Product-Suppliers',
        path: '/procurement-management/product-suppliers',
        permission: 'procurement.product_suppliers.view',
      },
      {
        title: 'Packing Lists',
        path: '/procurement-management/packing-lists',
        permission: 'procurement.packing_lists.view',
      },
      {
        title: 'SPO Allocations',
        path: '/procurement-management/spo-allocations',
        permission: 'procurement.spo_allocations.view',
      },
      {
        title: 'GRN',
        path: '/procurement-management/grn',
        permission: 'procurement.grn.view',
      },
      {
        title: 'Picking Lines',
        path: '/procurement-management/picking-lines',
        permission: 'procurement.picking_lines.view',
      },
      {
        title: 'Stock Inquiries',
        path: '/procurement-management/stock-inquiries',
        permission: 'procurement.stock_inquiries.view',
      },
      {
        title: 'Purchase Requests',
        path: '/procurement-management/purchase-requests',
        permission: 'procurement.purchase_requests.view',
      },
      {
        title: 'Sponsorship Forms',
        path: '/procurement-management/sponsorship-forms',
        permission: 'procurement.sponsorship_forms.view',
      },
    ],
  },
  {
    title: 'Inventory Management',
    icon: Warehouse,
    moduleKey: 'inventory',
    children: [
      {
        title: 'Warehouses',
        path: '/inventory-management/warehouses',
        permission: 'inventory.warehouses.view',
      },
      {
        title: 'Storage Zones',
        path: '/inventory-management/storage-zones',
        permission: 'inventory.storage_zones.view',
      },
      {
        title: 'Stock',
        path: '/inventory-management/stock',
        permission: 'inventory.stock.view',
      },
      {
        title: 'Stock Batches',
        path: '/inventory-management/stock-batches',
        permission: 'inventory.stock_batches.view',
      },
      {
        title: 'Stock Ledger',
        path: '/inventory-management/stock-ledger',
        permission: 'inventory.stock_ledger.view',
      },
    ],
  },
  {
    title: 'Marketing Management',
    icon: Megaphone,
    moduleKey: 'marketing',
    children: [
      {
        title: 'Promotions',
        children: [
          {
            title: 'All Promotions',
            path: '/marketing-management/promotions',
          },
          {
            title: 'Promotion Attachments',
            path: '/marketing-management/promotion-attachments',
          },
        ],
      },
      {
        title: 'Promotion Products',
        path: '/marketing-management/promotion-products',
      },
      {
        title: 'Campaigns',
        path: '/marketing-management/campaigns',
      },
    ],
  },
  {
    title: 'Forms Management',
    icon: FileText,
    moduleKey: 'forms',
    children: [
      {
        title: 'Forms',
        path: '/forms-management/forms',
      },
    ],
  },
  {
    title: 'Workflow Forms',
    icon: GitBranch,
    moduleKey: 'workflow_forms',
    children: [
      {
        title: 'Definitions',
        path: '/workflow-forms-management/definitions',
        permission: 'workflow_forms.definitions.view',
      },
    ],
  },
  {
    title: 'Resource Management',
    icon: Folder,
    moduleKey: 'resources',
    children: [
      {
        title: 'Files',
        path: '/resource-management/attachment-directories',
      },
      {
        title: 'Trash',
        path: '/resource-management/trash',
      },
      {
        title: 'Attachment Types',
        path: '/resource-management/attachment-types',
      },
    ],
  },
  {
    title: 'System Management',
    icon: Settings,
    moduleKey: 'base',
    children: [
      {
        title: 'App Store',
        path: '/system-management/app-store',
        permission: 'system.modules.manage',
      },
      {
        title: 'Module bundles',
        path: '/system-management/app-store/bundles',
        permission: 'system.modules.manage',
      },
      {
        title: 'Import Jobs',
        path: '/system-management/import-jobs',
      },
      {
        title: 'Import Logs',
        path: '/system-management/import-logs',
      },
      {
        title: 'Integration Logs',
        path: '/integration-management/integration-logs',
      },
      {
        title: 'Scheduled Tasks',
        path: '/system-management/scheduled-tasks',
      },
      {
        title: 'Outgoing Mails',
        path: '/system-management/outgoing-mails',
        permission: 'system.outgoing_mails.view',
      },
      {
        title: 'Work Calendar',
        path: '/system-management/work-calendar',
      },
      {
        title: 'Running Numbers',
        path: '/system-management/numbering-rules',
      },
    ],
  },
  {
    title: 'Authentication',
    icon: Shield,
    children: [
      {
        title: 'Sign In',
        path: '/signin',
      },
      {
        title: 'Check Email',
        path: '/signup',
      },
      {
        title: 'Reset Password',
        path: '/reset-password',
      },
      {
        title: '2FA',
        path: '/2fa',
      },
      { title: 'Welcome Message', path: '/auth/welcome-message' },
      { title: 'Account Deactivated', path: '/auth/account-deactivated' },
      { title: 'Error 404', path: '/error/404' },
      { title: 'Error 500', path: '/error/500' },
    ],
  },
];

export const MENU_MEGA: MenuConfig = [
  { title: 'Home', path: '/' },
  {
    title: 'Profiles',
    children: [
      {
        title: 'Profiles',
        children: [
          {
            children: [
              {
                title: 'Default',
                icon: Badge,
                path: '/public-profile/profiles/default',
              },
              {
                title: 'Creator',
                icon: Coffee,
                path: '/public-profile/profiles/creator',
              },
              {
                title: 'Company',
                icon: Building,
                path: '/public-profile/profiles/company',
              },
              {
                title: 'NFT',
                icon: Bitcoin,
                path: '/public-profile/profiles/nft',
              },
              {
                title: 'Blogger',
                icon: MessageSquare,
                path: '/public-profile/profiles/blogger',
              },
              {
                title: 'CRM',
                icon: Monitor,
                path: '/public-profile/profiles/crm',
              },
              {
                title: 'Gamer',
                icon: Ghost,
                path: '/public-profile/profiles/gamer',
              },
            ],
          },
          {
            children: [
              {
                title: 'Feeds',
                icon: Book,
                path: '/public-profile/profiles/feeds',
              },
              {
                title: 'Plain',
                icon: File,
                path: '/public-profile/profiles/plain',
              },
              {
                title: 'Modal',
                icon: SquareMousePointer,
                path: '/public-profile/profiles/modal',
              },
              {
                title: 'Freelancer',
                icon: Briefcase,
                path: '#',
                disabled: true,
              },
              { title: 'Developer', icon: Code, path: '#', disabled: true },
              { title: 'Team', icon: Users, path: '#', disabled: true },
              {
                title: 'Events',
                icon: CalendarCheck,
                path: '#',
                disabled: true,
              },
            ],
          },
        ],
      },
      {
        title: 'Other Pages',
        children: [
          {
            children: [
              {
                title: 'Projects - 3 Cols',
                icon: Layout,
                path: '/public-profile/projects/3-columns',
              },
              {
                title: 'Projects - 2 Cols',
                icon: Grid,
                path: '/public-profile/projects/2-columns',
              },
              { title: 'Works', icon: WorkIcon, path: '/public-profile/works' },
              {
                title: 'Teams',
                icon: PeopleIcon,
                path: '/public-profile/teams',
              },
              {
                title: 'Network',
                icon: Network,
                path: '/public-profile/network',
              },
              {
                title: 'Activity',
                icon: TrendingUp,
                path: '/public-profile/activity',
              },
              {
                title: 'Campaigns - Card',
                icon: LayoutGrid,
                path: '/public-profile/campaigns/card',
              },
            ],
          },
          {
            children: [
              {
                title: 'Campaigns - List',
                icon: Kanban,
                path: '/public-profile/campaigns/list',
              },
              { title: 'Empty', icon: FileText, path: '/public-profile/empty' },
              {
                title: 'Documents',
                icon: DocumentIcon,
                path: '#',
                disabled: true,
              },
              { title: 'Badges', icon: Award, path: '#', disabled: true },
              { title: 'Awards', icon: Gift, path: '#', disabled: true },
            ],
          },
        ],
      },
    ],
  },
  {
    title: 'My Account',
    children: [
      {
        title: 'General Pages',
        children: [
          { title: 'Integrations', icon: Plug, path: '/account/integrations' },
          {
            title: 'Notifications',
            icon: Bell,
            path: '/account/notifications',
          },
          { title: 'API Keys', icon: Key, path: '/account/api-keys' },
          { title: 'Appearance', icon: Eye, path: '/account/appearance' },
          {
            title: 'Invite a Friend',
            icon: UserCheck,
            path: '/account/invite-a-friend',
          },
          { title: 'Activity', icon: LifeBuoy, path: '/account/activity' },
          { title: 'Brand', icon: CheckCircle, disabled: true },
          { title: 'Get Paid', icon: Euro, disabled: true },
        ],
      },
      {
        title: 'Other pages',
        children: [
          {
            title: 'Account Home',
            children: [
              { title: 'Get Started', path: '/account/home/get-started' },
              { title: 'User Profile', path: '/user-management/account' },
              {
                title: 'Company Profile',
                path: '/account/home/company-profile',
              },
              { title: 'With Sidebar', path: '/account/home/settings-sidebar' },
              {
                title: 'Enterprise',
                path: '/account/home/settings-enterprise',
              },
              { title: 'Plain', path: '/account/home/settings-plain' },
              { title: 'Modal', path: '/account/home/settings-modal' },
            ],
          },
          {
            title: 'Billing',
            children: [
              { title: 'Basic Billing', path: '/account/billing/basic' },
              { title: 'Enterprise', path: '/account/billing/enterprise' },
              { title: 'Plans', path: '/account/billing/plans' },
              { title: 'Billing History', path: '/account/billing/history' },
              { title: 'Tax Info', disabled: true },
              { title: 'Invoices', disabled: true },
              { title: 'Gateaways', disabled: true },
            ],
          },
          {
            title: 'Security',
            children: [
              { title: 'Get Started', path: '/account/security/get-started' },
              {
                title: 'Security Overview',
                path: '/account/security/overview',
              },
              {
                title: 'IP Addresses',
                path: '/account/security/allowed-ip-addresses',
              },
              {
                title: 'Privacy Settings',
                path: '/account/security/privacy-settings',
              },
              {
                title: 'Device Management',
                path: '/account/security/device-management',
              },
              {
                title: 'Backup & Recovery',
                path: '/account/security/backup-and-recovery',
              },
              {
                title: 'Current Sessions',
                path: '/account/security/current-sessions',
              },
              { title: 'Security Log', path: '/account/security/security-log' },
            ],
          },
          {
            title: 'Members & Roles',
            children: [
              { title: 'Teams Starter', path: '/account/members/team-starter' },
              { title: 'Teams', path: '/account/members/teams' },
              { title: 'Team Info', path: '/account/members/team-info' },
              {
                title: 'Members Starter',
                path: '/account/members/members-starter',
              },
              { title: 'Team Members', path: '/account/members/team-members' },
              {
                title: 'Import Members',
                path: '/account/members/import-members',
              },
              { title: 'Roles', path: '/account/members/roles' },
              {
                title: 'Permissions - Toggler',
                path: '/account/members/permissions-toggle',
              },
              {
                title: 'Permissions - Check',
                path: '/account/members/permissions-check',
              },
            ],
          },
          {
            title: 'Other Pages',
            children: [
              { title: 'Integrations', path: '/account/integrations' },
              { title: 'Notifications', path: '/account/notifications' },
              { title: 'API Keys', path: '/account/api-keys' },
              { title: 'Appearance', path: '/account/appearance' },
              { title: 'Invite a Friend', path: '/account/invite-a-friend' },
              { title: 'Activity', path: '/account/activity' },
            ],
          },
        ],
      },
    ],
  },
  {
    title: 'Network',
    children: [
      {
        title: 'General Pages',
        children: [
          { title: 'Get Started', icon: Flag, path: '/network/get-started' },
          { title: 'Colleagues', icon: Users, path: '#', disabled: true },
          { title: 'Donators', icon: Heart, path: '#', disabled: true },
          { title: 'Leads', icon: Zap, path: '#', disabled: true },
        ],
      },
      {
        title: 'Other pages',
        children: [
          {
            title: 'User Cards',
            children: [
              { title: 'Mini Cards', path: '/network/user-cards/mini-cards' },
              { title: 'Team Members', path: '/network/user-cards/team-crew' },
              { title: 'Authors', path: '/network/user-cards/author' },
              { title: 'NFT Users', path: '/network/user-cards/nft' },
              { title: 'Social Users', path: '/network/user-cards/social' },
              { title: 'Gamers', path: '#', disabled: true },
            ],
          },
          {
            title: 'User Base',
            badge: 'Datatables',
            children: [
              { title: 'Team Crew', path: '/network/user-table/team-crew' },
              { title: 'App Roster', path: '/network/user-table/app-roster' },
              {
                title: 'Market Authors',
                path: '/network/user-table/market-authors',
              },
              { title: 'SaaS Users', path: '/network/user-table/saas-users' },
              {
                title: 'Store Clients',
                path: '/network/user-table/store-clients',
              },
              { title: 'Visitors', path: '/network/user-table/visitors' },
            ],
          },
        ],
      },
    ],
  },
  {
    title: 'Apps',
    children: [
      {
        title: 'Store - Client',
        children: [
          {
            children: [
              { title: 'Home', path: '/store-client/home' },
              {
                title: 'Search Results - Grid',
                path: '/store-client/search-results-grid',
              },
              {
                title: 'Search Results - List',
                path: '/store-client/search-results-list',
              },
              {
                title: 'Product Details',
                path: '/store-client/product-details',
              },
              { title: 'Wishlist', path: '/store-client/wishlist' },
              { title: 'My Orders', path: '/store-client/my-orders' },
            ],
          },
          {
            children: [
              {
                title: 'Checkout - Order Summary',
                path: '/store-client/checkout/order-summary',
              },
              {
                title: 'Checkout - Shipping Info',
                path: '/store-client/checkout/shipping-info',
              },
              {
                title: 'Checkout - Payment Method',
                path: '/store-client/checkout/payment-method',
              },
              {
                title: 'Checkout - Order Placed',
                path: '/store-client/checkout/order-placed',
              },
              { title: 'Order Receipt', path: '/store-client/order-receipt' },
            ],
          },
        ],
      },
      {
        title: 'User Management',
        children: [
          {
            children: [
              {
                title: 'Administrative Users',
                path: '/user-management/users',
              },
              {
                title: 'Roles',
                path: '/user-management/roles',
              },
              {
                title: 'Permissions',
                path: '/user-management/permissions',
              },
              {
                title: 'Account',
                path: '/user-management/account',
              },
              {
                title: 'Logs',
                path: '/user-management/logs',
              },
              {
                title: 'Settings',
                path: '/user-management/settings',
              },
            ],
          },
        ],
      },
    ],
  },
];

export const MENU_MEGA_MOBILE: MenuConfig = [
  { title: 'Home', path: '/' },
  {
    title: 'Profiles',
    children: [
      {
        title: 'Profiles',
        children: [
          {
            title: 'Default',
            icon: Badge,
            path: '/public-profile/profiles/default',
          },
          {
            title: 'Creator',
            icon: Coffee,
            path: '/public-profile/profiles/creator',
          },
          {
            title: 'Company',
            icon: Building,
            path: '/public-profile/profiles/company',
          },
          { title: 'NFT', icon: Bitcoin, path: '/public-profile/profiles/nft' },
          {
            title: 'Blogger',
            icon: MessageSquare,
            path: '/public-profile/profiles/blogger',
          },
          { title: 'CRM', icon: Monitor, path: '/public-profile/profiles/crm' },
          {
            title: 'Gamer',
            icon: Ghost,
            path: '/public-profile/profiles/gamer',
          },
          {
            title: 'Feeds',
            icon: Book,
            path: '/public-profile/profiles/feeds',
          },
          {
            title: 'Plain',
            icon: File,
            path: '/public-profile/profiles/plain',
          },
          {
            title: 'Modal',
            icon: SquareMousePointer,
            path: '/public-profile/profiles/modal',
          },
          { title: 'Freelancer', icon: Briefcase, path: '#', disabled: true },
          { title: 'Developer', icon: Code, path: '#', disabled: true },
          { title: 'Team', icon: Users, path: '#', disabled: true },
          { title: 'Events', icon: CalendarCheck, path: '#', disabled: true },
        ],
      },
      {
        title: 'Other Pages',
        children: [
          {
            title: 'Projects - 3 Cols',
            icon: Layout,
            path: '/public-profile/projects/3-columns',
          },
          {
            title: 'Projects - 2 Cols',
            icon: Grid,
            path: '/public-profile/projects/2-columns',
          },
          { title: 'Works', icon: WorkIcon, path: '/public-profile/works' },
          { title: 'Teams', icon: PeopleIcon, path: '/public-profile/teams' },
          { title: 'Network', icon: Network, path: '/public-profile/network' },
          {
            title: 'Activity',
            icon: TrendingUp,
            path: '/public-profile/activity',
          },
          {
            title: 'Campaigns - Card',
            icon: LayoutGrid,
            path: '/public-profile/campaigns/card',
          },
          {
            title: 'Campaigns - List',
            icon: Kanban,
            path: '/public-profile/campaigns/list',
          },
          { title: 'Empty', icon: FileText, path: '/public-profile/empty' },
          { title: 'Documents', icon: DocumentIcon, path: '#', disabled: true },
          { title: 'Badges', icon: Award, path: '#', disabled: true },
          { title: 'Awards', icon: Gift, path: '#', disabled: true },
        ],
      },
    ],
  },
  {
    title: 'My Account',
    children: [
      {
        title: 'General Pages',
        children: [
          { title: 'Integrations', icon: Plug, path: '/account/integrations' },
          {
            title: 'Notifications',
            icon: Bell,
            path: '/account/notifications',
          },
          { title: 'API Keys', icon: Key, path: '/account/api-keys' },
          { title: 'Appearance', icon: Eye, path: '/account/appearance' },
          {
            title: 'Invite a Friend',
            icon: UserCheck,
            path: '/account/invite-a-friend',
          },
          { title: 'Activity', icon: LifeBuoy, path: '/account/activity' },
          { title: 'Brand', icon: CheckCircle, disabled: true },
          { title: 'Get Paid', icon: Euro, disabled: true },
        ],
      },
      {
        title: 'Other pages',
        children: [
          {
            title: 'Account Home',
            children: [
              { title: 'Get Started', path: '/account/home/get-started' },
              { title: 'User Profile', path: '/user-management/account' },
              {
                title: 'Company Profile',
                path: '/account/home/company-profile',
              },
              { title: 'With Sidebar', path: '/account/home/settings-sidebar' },
              {
                title: 'Enterprise',
                path: '/account/home/settings-enterprise',
              },
              { title: 'Plain', path: '/account/home/settings-plain' },
              { title: 'Modal', path: '/account/home/settings-modal' },
            ],
          },
          {
            title: 'Billing',
            children: [
              { title: 'Basic Billing', path: '/account/billing/basic' },
              { title: 'Enterprise', path: '/account/billing/enterprise' },
              { title: 'Plans', path: '/account/billing/plans' },
              { title: 'Billing History', path: '/account/billing/history' },
              { title: 'Tax Info', disabled: true },
              { title: 'Invoices', disabled: true },
              { title: 'Gateaways', disabled: true },
            ],
          },
          {
            title: 'Security',
            children: [
              { title: 'Get Started', path: '/account/security/get-started' },
              {
                title: 'Security Overview',
                path: '/account/security/overview',
              },
              {
                title: 'IP Addresses',
                path: '/account/security/allowed-ip-addresses',
              },
              {
                title: 'Privacy Settings',
                path: '/account/security/privacy-settings',
              },
              {
                title: 'Device Management',
                path: '/account/security/device-management',
              },
              {
                title: 'Backup & Recovery',
                path: '/account/security/backup-and-recovery',
              },
              {
                title: 'Current Sessions',
                path: '/account/security/current-sessions',
              },
              { title: 'Security Log', path: '/account/security/security-log' },
            ],
          },
          {
            title: 'Members & Roles',
            children: [
              { title: 'Teams Starter', path: '/account/members/team-starter' },
              { title: 'Teams', path: '/account/members/teams' },
              { title: 'Team Info', path: '/account/members/team-info' },
              {
                title: 'Members Starter',
                path: '/account/members/members-starter',
              },
              { title: 'Team Members', path: '/account/members/team-members' },
              {
                title: 'Import Members',
                path: '/account/members/import-members',
              },
              { title: 'Roles', path: '/account/members/roles' },
              {
                title: 'Permissions - Toggler',
                path: '/account/members/permissions-toggle',
              },
              {
                title: 'Permissions - Check',
                path: '/account/members/permissions-check',
              },
            ],
          },
          {
            title: 'Other Pages',
            children: [
              { title: 'Integrations', path: '/account/integrations' },
              { title: 'Notifications', path: '/account/notifications' },
              { title: 'API Keys', path: '/account/api-keys' },
              { title: 'Appearance', path: '/account/appearance' },
              { title: 'Invite a Friend', path: '/account/invite-a-friend' },
              { title: 'Activity', path: '/account/activity' },
            ],
          },
        ],
      },
    ],
  },
  {
    title: 'Network',
    children: [
      {
        title: 'General Pages',
        children: [
          { title: 'Get Started', icon: Flag, path: '/network/get-started' },
          { title: 'Colleagues', icon: Users, path: '#', disabled: true },
          { title: 'Donators', icon: Heart, path: '#', disabled: true },
          { title: 'Leads', icon: Zap, path: '#', disabled: true },
        ],
      },
      {
        title: 'Other pages',
        children: [
          {
            title: 'User Cards',
            children: [
              { title: 'Mini Cards', path: '/network/user-cards/mini-cards' },
              { title: 'Team Members', path: '/network/user-cards/team-crew' },
              { title: 'Authors', path: '/network/user-cards/author' },
              { title: 'NFT Users', path: '/network/user-cards/nft' },
              { title: 'Social Users', path: '/network/user-cards/social' },
              { title: 'Gamers', path: '#', disabled: true },
            ],
          },
          {
            title: 'User Base',
            badge: 'Datatables',
            children: [
              { title: 'Team Crew', path: '/network/user-table/team-crew' },
              { title: 'App Roster', path: '/network/user-table/app-roster' },
              {
                title: 'Market Authors',
                path: '/network/user-table/market-authors',
              },
              { title: 'SaaS Users', path: '/network/user-table/saas-users' },
              {
                title: 'Store Clients',
                path: '/network/user-table/store-clients',
              },
              { title: 'Visitors', path: '/network/user-table/visitors' },
            ],
          },
        ],
      },
    ],
  },
  {
    title: 'User Management',
    icon: Users,
    children: [
      {
        title: 'Users',
        path: '/user-management/users',
      },
      {
        title: 'Roles',
        path: '/user-management/roles',
      },
      {
        title: 'Permissions',
        path: '/user-management/permissions',
      },
      {
        title: 'Account',
        path: '/user-management/account',
      },
      {
        title: 'Logs',
        path: '/user-management/logs',
      },
      {
        title: 'Settings',
        path: '/user-management/settings',
      },
    ],
  },
  {
    title: 'Store - Client',
    children: [
      { title: 'Home', path: '/store-client/home' },
      {
        title: 'Search Results - Grid',
        path: '/store-client/search-results-grid',
      },
      {
        title: 'Search Results - List',
        path: '/store-client/search-results-list',
      },
      { title: 'Product Details', path: '/store-client/product-details' },
      { title: 'Wishlist', path: '/store-client/wishlist' },
      {
        title: 'Checkout',
        children: [
          {
            title: 'Order Summary',
            path: '/store-client/checkout/order-summary',
          },
          {
            title: 'Shipping Info',
            path: '/store-client/checkout/shipping-info',
          },
          {
            title: 'Payment Method',
            path: '/store-client/checkout/payment-method',
          },
          {
            title: 'Order Placed',
            path: '/store-client/checkout/order-placed',
          },
        ],
      },
      { title: 'My Orders', path: '/store-client/my-orders' },
      { title: 'Order Receipt', path: '/store-client/order-receipt' },
    ],
  },
];

export const MENU_HELP: MenuConfig = [
  {
    title: 'Getting Started',
    icon: Coffee,
    path: 'https://keenthemes.com/metronic/tailwind/docs/getting-started/installation',
  },
  {
    title: 'Support Forum',
    icon: AlertCircle,
    children: [
      {
        title: 'All Questions',
        icon: FileQuestion,
        path: 'https://devs.keenthemes.com',
      },
      {
        title: 'Popular Questions',
        icon: Star,
        path: 'https://devs.keenthemes.com/popular',
      },
      {
        title: 'Ask Question',
        icon: HelpCircle,
        path: 'https://devs.keenthemes.com/question/create',
      },
    ],
  },
  {
    title: 'Licenses & FAQ',
    icon: Captions,
    path: 'https://keenthemes.com/metronic/tailwind/docs/getting-started/license',
  },
  {
    title: 'Documentation',
    icon: FileQuestion,
    path: 'https://keenthemes.com/metronic/tailwind/docs',
  },
  { separator: true },
  { title: 'Contact Us', icon: Share2, path: 'https://keenthemes.com/contact' },
];

export const MENU_ROOT: MenuConfig = [
  {
    title: 'Public Profile',
    icon: UserCircle,
    rootPath: '/public-profile/',
    path: '/public-profile/profiles/default',
    childrenIndex: 2,
  },
  {
    title: 'Account',
    icon: Settings,
    rootPath: '/account/',
    path: '/',
    childrenIndex: 3,
  },
  {
    title: 'Network',
    icon: Users,
    rootPath: '/network/',
    path: '/network/get-started',
    childrenIndex: 4,
  },
  {
    title: 'Authentication',
    icon: Shield,
    rootPath: '/authentication/',
    path: '/authentication/get-started',
    childrenIndex: 5,
  },
  {
    title: 'Store - Client',
    icon: ShoppingCart,
    rootPath: '/store-client/',
    path: '/store-client/home',
    childrenIndex: 6,
  },
  {
    title: 'User Management',
    icon: ShieldUser,
    rootPath: '/user-management/',
    path: '/user-management/users',
    childrenIndex: 7,
  },
];
