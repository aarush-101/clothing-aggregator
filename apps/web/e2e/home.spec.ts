import { expect, test } from '@playwright/test';

test.describe('home page', () => {
  test('is a wordmark, one search field and three examples', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('link', { name: /Marle/ })).toBeVisible();
    await expect(page.getByRole('searchbox')).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Search' })).toBeVisible();

    const examples = page.getByRole('list').filter({ hasText: 'linen' }).first();
    await expect(examples.getByRole('button')).toHaveCount(3);
  });

  test('shows no catalogue, categories or promotions before a search', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByTestId('product-card')).toHaveCount(0);
    await expect(page.getByTestId('product-grid')).toHaveCount(0);
    // No product photography, because nothing has been fetched yet.
    await expect(page.locator('img')).toHaveCount(0);
    await expect(page.getByRole('navigation')).toHaveCount(0);
    // The only heading on the page is the visually hidden "Example searches"
    // label; there is no visible catalogue furniture.
    await expect(page.getByRole('heading')).toHaveText(['Example searches']);
  });

  test('puts the cursor in the search field on arrival', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('searchbox')).toBeFocused();
  });

  test('is operable by keyboard alone', async ({ page }) => {
    await page.goto('/');

    await page.keyboard.type('navy merino crew knit');
    await page.keyboard.press('Enter');

    await expect(page).toHaveURL(/\/search\?q=navy/);
    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      'navy merino crew knit',
    );
  });

  test('an example search runs a real search', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Cream oversized overshirt/ }).click();

    await expect(page).toHaveURL(/\/search\?q=/);
    await expect(page.getByTestId('product-card').first()).toBeVisible();
  });
});
