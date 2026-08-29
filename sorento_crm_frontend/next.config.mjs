/** @type {import('next').NextConfig} */
const nextConfig = {
  // For local development, basePath is '/'
  // This file will be overwritten during deployment with the appropriate basePath
  images: {},
  output: 'standalone',
  // `next dev` and `next start` share `.next/` by default, so starting a dev server in
  // this directory REPLACES the production build a running `next start` is serving and
  // takes it down with a client-side exception. Set NEXT_DIST_DIR=.next-dev when running
  // a dev server alongside a prod one so the two never write to the same directory.
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  // Don't fail build on ESLint errors (warnings will still be shown)
  // This allows Docker builds to complete even with linting issues
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Don't fail build on TypeScript errors (only for build, not dev)
  typescript: {
    ignoreBuildErrors: false, // Keep this false to catch real TS errors
  },
  // Build optimizations for faster Docker builds
  swcMinify: true, // Use SWC minifier (faster than Terser)
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production' ? {
      exclude: ['error', 'warn'], // Keep errors and warnings in production
    } : false,
  },
  // Optimize production builds
  productionBrowserSourceMaps: false, // Disable source maps in production for faster builds
  // Reduce build output size
  poweredByHeader: false,
  reactStrictMode: true,
  // Hosts (besides localhost) allowed to load /_next/* from the dev server: Tailscale name,
  // LAN IP, etc. Comma-separated; wildcards like *.ts.net allowed. Dev only, ignored by builds.
  allowedDevOrigins: (process.env.NEXT_DEV_ALLOWED_ORIGINS ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean),
  // Proxy API requests to FastAPI backend in development
  async rewrites() {
    // Only apply rewrites in development mode
    if (process.env.NODE_ENV === 'development') {
      return [
        {
          source: '/api/v1/:path*',
          destination: `${process.env.FASTAPI_INTERNAL_URL ?? 'http://localhost:8000'}/api/v1/:path*`,
        },
      ];
    }
    return [];
  },
};

export default nextConfig;
