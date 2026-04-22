/**
 * Playwright demo-video driver.
 *
 * Walks every major surface the judges need to see (live feed, side
 * panels, WebSocket status, verify click, mobile viewport) in a scripted
 * order so the video recording is reproducible. Invoked via
 * `scripts/record_demo_video.sh`.
 */
import { expect, test } from '@playwright/test';

test.use({ video: 'on' });

test('demo walkthrough', async ({ page }) => {
  test.slow();
  // 1. Dashboard loads.
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Live feed/i })).toBeVisible();
  await page.waitForTimeout(2_000);

  // 2. Side panels show up.
  await expect(page.getByText(/Swarm health/i)).toBeVisible();
  await expect(page.getByText(/Model usage/i)).toBeVisible();
  await expect(page.getByText(/Activity \(last 24h\)/i)).toBeVisible();
  await page.waitForTimeout(2_000);

  // 3. WebSocket status.
  await expect(page.getByTestId('ws-status')).toBeVisible();
  await page.waitForTimeout(2_000);

  // 4. Click the first Verify link (opens BscScan verify endpoint).
  const verifyButton = page.locator('[data-testid^="verify-"]').first();
  if (await verifyButton.count()) {
    await verifyButton.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1_500);
  }

  // 5. Mobile viewport check.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(2_000);
  await expect(page.getByRole('heading', { name: /Live feed/i })).toBeVisible();
});
