/**
 * Render SwarmScout logo SVG to a 512x512 PNG and a 160x160 PNG for the
 * DoraHacks BUIDL form. Run with:
 *
 *   cd web
 *   pnpm exec playwright test tests/e2e/render_logo.spec.ts --project=chromium-desktop --reporter=list
 *
 * Output files are written to the repo root:
 *   branding/logo_512.png
 *   branding/logo_160.png
 */
import { test } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const SVG_PATH = path.join(REPO_ROOT, 'branding', 'logo.svg');
const OUT_512 = path.join(REPO_ROOT, 'branding', 'logo_512.png');
const OUT_160 = path.join(REPO_ROOT, 'branding', 'logo_160.png');

test('render logo PNGs', async ({ browser }) => {
  test.setTimeout(30_000);
  const svg = fs.readFileSync(SVG_PATH, 'utf8');

  for (const [size, out] of [[512, OUT_512], [160, OUT_160]] as const) {
    const context = await browser.newContext({
      viewport: { width: size, height: size },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    const html = `<!doctype html><html><head><style>
      html,body{margin:0;padding:0;background:transparent}
      svg{width:${size}px;height:${size}px;display:block}
    </style></head><body>${svg}</body></html>`;
    await page.setContent(html, { waitUntil: 'load' });
    const element = await page.$('svg');
    if (!element) throw new Error('svg not found');
    const buf = await element.screenshot({ omitBackground: true, type: 'png' });
    fs.writeFileSync(out, buf);
    await context.close();
  }
});
