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
};

export default nextConfig;
