/** @type {import('next').NextConfig} */
const nextConfig = {
  // For local development, basePath is '/'
  // This file will be overwritten during deployment with the appropriate basePath
  images: {},
  output: 'standalone',
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
  // Proxy API requests to FastAPI backend in development
  async rewrites() {
    // Only apply rewrites in development mode
    if (process.env.NODE_ENV === 'development' && !process.env.NEXT_PUBLIC_API_URL) {
      return [
        {
          source: '/api/v1/:path*',
          destination: 'http://localhost:8000/api/v1/:path*',
        },
      ];
    }
    return [];
  },
};

export default nextConfig;
