import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Next blocks cross-origin dev requests by default; local tooling and the
  // Playwright suite reach the dev server over 127.0.0.1 as well as localhost.
  allowedDevOrigins: ['localhost', '127.0.0.1'],
  // Produces a self-contained server bundle for the Docker image; Vercel
  // ignores this and uses its own build output.
  output: 'standalone',
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-Frame-Options', value: 'DENY' },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
        ],
      },
    ];
  },
};

export default nextConfig;
