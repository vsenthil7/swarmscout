/**
 * SwarmScout demo-video recorder.
 *
 * Pure-static Playwright tour that records a ~2-minute walkthrough of
 * the submission artefacts as a .webm. Does NOT require the backend,
 * Redis, Postgres, or the Next.js dev server. Points the browser at
 * local static files (coverage HTML reports, architecture docs rendered
 * via a tiny data: URL) plus the public GitHub repo.
 *
 * Output: web/test-results/**\/video.webm (Playwright default path);
 * record_demo_video.sh copies it up to demo.webm and ffmpeg-encodes to mp4.
 *
 * Uses only things that are actually present on disk right now:
 *   - GitHub repo page (43+ commits, README, source tree)
 *   - Python htmlcov/index.html
 *   - Frontend web/coverage/index.html
 *   - Forge coverage text snapshot embedded in the title-card
 *
 * Resolution: 1280x720 (YouTube-friendly, keeps file size low).
 * Target duration: ~2 min. Hard ceiling: 3 min.
 */
import { test, expect } from '@playwright/test';
import path from 'node:path';

test.describe.configure({ mode: 'serial' });
test.use({
  viewport: { width: 1280, height: 720 },
  video: { mode: 'on', size: { width: 1280, height: 720 } },
  launchOptions: { slowMo: 200 },
});

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const PYCOV = `file:///${path.join(REPO_ROOT, 'htmlcov', 'index.html').replace(/\\/g, '/')}`;
const TSCOV = `file:///${path.join(REPO_ROOT, 'web', 'coverage', 'index.html').replace(/\\/g, '/')}`;
const GITHUB = 'https://github.com/vsenthil7/swarmscout';

const TITLE_HTML = `data:text/html;charset=utf-8,${encodeURIComponent(`
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>SwarmScout</title>
  <style>
    :root { color-scheme: dark; }
    html,body { margin:0; padding:0; background:#0b0f1a; color:#e6eaf5; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI"; }
    .wrap { width:1100px; margin: 60px auto; padding: 48px 56px; background: linear-gradient(135deg, #0f1629 0%, #121a33 100%); border:1px solid #223; border-radius:18px; box-shadow: 0 30px 90px rgba(0,0,0,.4); }
    h1 { font-size: 62px; margin: 0 0 8px; letter-spacing:-0.02em; background: linear-gradient(90deg, #60a5fa 0%, #a78bfa 50%, #f472b6 100%); -webkit-background-clip: text; background-clip: text; color: transparent; }
    .sub { font-size: 22px; color:#9fb0d0; margin-bottom: 32px; }
    .pill-row { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:28px; }
    .pill { display:inline-flex; align-items:center; gap:8px; padding: 8px 14px; background:#1a2340; border:1px solid #2c3b66; border-radius:999px; font-size:14px; color:#c7d3ee; }
    .pill strong { color:#5eead4; font-weight:700; }
    .grid { display:grid; grid-template-columns: 1fr 1fr; gap:20px; margin-top: 24px; }
    .card { padding:20px 22px; background:#0b1228; border:1px solid #1b2547; border-radius:12px; }
    .card h3 { margin:0 0 10px; font-size:15px; color:#9fb0d0; font-weight:600; text-transform:uppercase; letter-spacing:0.1em; }
    .big { font-size: 44px; font-weight:700; color:#e6eaf5; }
    .big small { font-size:18px; color:#9fb0d0; font-weight:400; margin-left:8px; }
    .foot { margin-top:36px; font-size:14px; color:#6f7ea5; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>SwarmScout</h1>
    <div class="sub">A 5-agent decentralised swarm for Four.meme alpha discovery &middot; on-chain provenance &middot; multi-LLM routing</div>
    <div class="pill-row">
      <span class="pill">HACK0015 &middot; <strong>Four.Meme AI Sprint</strong></span>
      <span class="pill">Bounty &middot; <strong>DGrid AI Gateway</strong></span>
      <span class="pill"><strong>BNB Testnet</strong></span>
      <span class="pill">Built by <strong>vsenthil7</strong></span>
    </div>
    <div class="grid">
      <div class="card"><h3>Python tests</h3><div class="big">338 <small>passing</small></div></div>
      <div class="card"><h3>TypeScript tests</h3><div class="big">46 <small>passing</small></div></div>
      <div class="card"><h3>Solidity tests</h3><div class="big">19 <small>passing</small></div></div>
      <div class="card"><h3>Git commits</h3><div class="big">47 <small>on main</small></div></div>
    </div>
    <div class="foot">Architecture: Hunter &rarr; Social &rarr; Chain &rarr; Risk &rarr; Narrator &rarr; Telegram &middot; Redis Streams bus &middot; FindingsRegistry.sol anchoring every envelope</div>
  </div>
</body>
</html>
`)}`;

const COVERAGE_SUMMARY_HTML = `data:text/html;charset=utf-8,${encodeURIComponent(`
<!doctype html>
<html><head><meta charset="utf-8"><title>Coverage</title>
<style>
  :root{color-scheme:dark}
  body{margin:0;background:#0b0f1a;color:#e6eaf5;font-family:ui-sans-serif,system-ui,"Segoe UI";padding:40px 60px}
  h1{font-size:40px;background:linear-gradient(90deg,#60a5fa,#a78bfa);-webkit-background-clip:text;background-clip:text;color:transparent;margin:0 0 24px}
  table{width:100%;border-collapse:collapse;font-size:16px}
  th,td{padding:12px 16px;text-align:left;border-bottom:1px solid #1b2547}
  th{color:#9fb0d0;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;font-size:13px}
  .pct{font-family:ui-monospace,Consolas,Menlo;font-weight:600}
  .g{color:#5eead4}.y{color:#fbbf24}
  .cap{margin-top:28px;font-size:14px;color:#6f7ea5}
</style></head><body>
<h1>Coverage &middot; all three runtimes</h1>
<table>
  <thead><tr><th>Runtime</th><th>Tests</th><th>Lines</th><th>Branches</th><th>Gate</th></tr></thead>
  <tbody>
    <tr><td>Python &middot; pytest</td><td>338</td><td class="pct y">89.23%</td><td class="pct y">~97%</td><td>100% target</td></tr>
    <tr><td>TypeScript &middot; Vitest</td><td>46</td><td class="pct g">100.00%</td><td class="pct g">94.66%</td><td class="g">\u2705 met</td></tr>
    <tr><td>Solidity &middot; Foundry</td><td>19</td><td class="pct g">100.00%</td><td class="pct g">100.00%</td><td class="g">\u2705 met</td></tr>
  </tbody>
</table>
<p class="cap">Solidity: FindingsRegistry.sol &middot; 15 unit + 2 fuzz (\u00d71000 runs) + 2 invariants (\u00d78192 calls) &middot; 0 reverts</p>
</body></html>
`)}`;

test('demo recording', async ({ page }) => {
  test.setTimeout(240_000); // 4 min hard cap (recording itself is ~2 min)

  // -------- Scene 1: Title card (8s) ---------------------------------------
  await page.goto(TITLE_HTML);
  await expect(page.getByText('SwarmScout')).toBeVisible();
  await page.waitForTimeout(8_000);

  // -------- Scene 2: Coverage summary table (8s) ---------------------------
  await page.goto(COVERAGE_SUMMARY_HTML);
  await expect(page.getByText('all three runtimes')).toBeVisible();
  await page.waitForTimeout(8_000);

  // -------- Scene 3: GitHub repo landing (10s) -----------------------------
  await page.goto(GITHUB, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(5_000);
  // Scroll slowly through the README.
  await page.evaluate(() => window.scrollBy({ top: 400, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);
  await page.evaluate(() => window.scrollBy({ top: 400, behavior: 'smooth' }));
  await page.waitForTimeout(2_000);

  // -------- Scene 4: Commit history (10s) ----------------------------------
  await page.goto(`${GITHUB}/commits/main`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4_000);
  await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);
  await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);

  // -------- Scene 5: FindingsRegistry contract source (10s) ----------------
  await page.goto(`${GITHUB}/blob/main/contracts/src/FindingsRegistry.sol`, {
    waitUntil: 'domcontentloaded',
  });
  await page.waitForTimeout(4_000);
  await page.evaluate(() => window.scrollBy({ top: 400, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);
  await page.evaluate(() => window.scrollBy({ top: 400, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);

  // -------- Scene 6: Python coverage HTML (10s) ----------------------------
  try {
    await page.goto(PYCOV, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4_000);
    await page.evaluate(() => window.scrollBy({ top: 500, behavior: 'smooth' }));
    await page.waitForTimeout(3_000);
    await page.evaluate(() => window.scrollBy({ top: 500, behavior: 'smooth' }));
    await page.waitForTimeout(3_000);
  } catch {
    // If htmlcov wasn't generated, skip without breaking the recording.
  }

  // -------- Scene 7: Frontend coverage HTML (10s) --------------------------
  try {
    await page.goto(TSCOV, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4_000);
    await page.evaluate(() => window.scrollBy({ top: 400, behavior: 'smooth' }));
    await page.waitForTimeout(3_000);
    await page.evaluate(() => window.scrollBy({ top: 400, behavior: 'smooth' }));
    await page.waitForTimeout(3_000);
  } catch {
    // Same graceful degradation.
  }

  // -------- Scene 8: Architecture doc on GitHub (10s) ----------------------
  await page.goto(`${GITHUB}/blob/main/docs/02_Architecture.md`, {
    waitUntil: 'domcontentloaded',
  });
  await page.waitForTimeout(4_000);
  await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);
  await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);

  // -------- Scene 9: Requirements traceability (10s) -----------------------
  await page.goto(`${GITHUB}/blob/main/docs/TRACEABILITY.md`, {
    waitUntil: 'domcontentloaded',
  });
  await page.waitForTimeout(4_000);
  await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);
  await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);

  // -------- Scene 10: Phase 2 status rollup (10s) --------------------------
  await page.goto(
    `${GITHUB}/blob/main/Project-Status/SwarmScout_Status_Rollup_Phase2.md`,
    { waitUntil: 'domcontentloaded' },
  );
  await page.waitForTimeout(4_000);
  await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);
  await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
  await page.waitForTimeout(3_000);

  // -------- Scene 11: Closing card (5s) ------------------------------------
  await page.goto(TITLE_HTML);
  await expect(page.getByText('SwarmScout')).toBeVisible();
  await page.waitForTimeout(5_000);
});
