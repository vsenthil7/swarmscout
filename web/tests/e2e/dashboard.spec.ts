/**
 * Playwright E2E smoke — dashboard renders and shows every major surface.
 *
 * Maps to TC-E06 (feed loads), TC-E06m (mobile viewport), TC-E07 (side
 * panels visible), TC-E09 (websocket status pill). Run against a live
 * dashboard via PLAYWRIGHT_BASE_URL.
 */
import { expect, test } from '@playwright/test';

test.describe('dashboard smoke', () => {
  // TC-E06 — loads feed
  test('loads the feed', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /Live feed/i })).toBeVisible();
  });

  // TC-E06m — mobile viewport
  test('loads the feed on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /Live feed/i })).toBeVisible();
  });

  // TC-E07 — side panels present
  test('renders the side panels', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(/Swarm health/i)).toBeVisible();
    await expect(page.getByText(/Model usage/i)).toBeVisible();
    await expect(page.getByText(/Activity \(last 24h\)/i)).toBeVisible();
  });

  // TC-E09 — WebSocket status pill appears
  test('shows websocket status pill', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('ws-status')).toBeVisible();
  });
});
