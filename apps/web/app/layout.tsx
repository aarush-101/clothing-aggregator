import type { Metadata, Viewport } from 'next';

import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Marle — Menswear search',
    template: '%s — Marle',
  },
  description:
    'Describe what you are looking for and Marle searches a regularly refreshed menswear catalogue across retailers.',
  robots: { index: true, follow: true },
  openGraph: {
    title: 'Marle — Menswear search',
    description:
      'Describe what you are looking for and Marle searches a regularly refreshed menswear catalogue across retailers.',
    type: 'website',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#faf9f6' },
    { media: '(prefers-color-scheme: dark)', color: '#131210' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-AU" suppressHydrationWarning>
      <body className="min-h-dvh antialiased">
        <a
          href="#main"
          className="sr-only rounded-sm bg-accent px-4 py-2 text-accent-foreground focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50"
        >
          Skip to content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
