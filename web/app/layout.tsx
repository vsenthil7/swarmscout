import type { Metadata } from 'next';
import './globals.css';

/** Next.js route metadata — populates &lt;title&gt; and &lt;meta name="description"&gt; for every page. */
export const metadata: Metadata = {
  title: 'SwarmScout — Four.meme alpha feed',
  description:
    'Decentralised agent swarm for Four.meme alpha discovery. Every brief is hash-anchored on BNB Testnet.',
};

/**
 * Root layout — wraps every route with a consistent header + footer.
 *
 * Next.js requires a default export here; this is the container for every
 * page's content.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-slate-100 antialiased">
        <header className="border-b border-border px-6 py-4">
          <div className="mx-auto flex max-w-7xl items-center justify-between">
            <a href="/" className="flex items-center gap-3">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-accent text-black font-bold">
                S
              </span>
              <span className="text-lg font-semibold tracking-tight">SwarmScout</span>
            </a>
            <nav className="flex gap-6 text-sm text-slate-400">
              <a className="hover:text-slate-100" href="/">
                Feed
              </a>
              <a
                className="hover:text-slate-100"
                href="https://github.com/"
                target="_blank"
                rel="noreferrer"
              >
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
        <footer className="mt-16 border-t border-border px-6 py-6 text-sm text-slate-500">
          <div className="mx-auto max-w-7xl">
            SwarmScout — every brief is hash-anchored on BNB Testnet. Click Verify on any brief.
          </div>
        </footer>
      </body>
    </html>
  );
}
