// From webapp_frontend: node --test scripts/test_discovery_bookmarks_and_planning.cjs
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {chromium, expect} = require('@playwright/test');
const origin = 'http://127.0.0.1:5187';
let server, browser;
before(async () => {
  server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5187', '--strictPort'], {stdio: 'ignore'});
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(origin)).ok) break; } catch {}
    if (server.exitCode !== null) throw new Error('Vite failed to start');
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  browser = await chromium.launch({headless: true});
});
after(async () => { await browser?.close(); server?.kill(); });

async function openApp(t, path, lang = 'en', now = '2026-10-02T21:50:00Z') {
  const context = await browser.newContext({timezoneId: 'Europe/Paris', locale: 'en-GB', viewport: {width: 390, height: 844}});
  const page = await context.newPage();
  const errors = [], plans = [], saves = [], saved = new Set(['saved']);
  page.on('pageerror', error => errors.push(error.message));
  t.after(async () => { await context.close(); assert.deepEqual(errors, []); });
  await page.clock.setFixedTime(new Date(now));
  await page.addInitScript(() => localStorage.setItem('telegram_auth_token', 'test-session'));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.fulfill({body: '', contentType: 'application/javascript'});
    if (!url.pathname.startsWith('/api/')) return route.continue();
    assert.equal(route.request().headers().authorization, 'Bearer test-session');
    if (url.pathname === '/api/explore') return route.fulfill({json: {categories: [{id: 'french', title: 'French', topics: [{id: 'watch', title: 'Watch', items: ['saved', 'fresh'].map((id, order) => ({
      id, content_id: id, title: id === 'saved' ? 'Already in Library' : 'New lesson', type: 'video', order,
      published: true, native_ref: '/youtube-watch?video_id=' + (id === 'saved' ? 'abcdefghijk' : 'lmnopqrstuv'), is_saved: saved.has(id),
    }))}]}], clubs: []}});
    if (url.pathname === '/api/user-content') {
      const id = route.request().postDataJSON().content_id;
      saves.push(id); saved.add(id);
      return route.fulfill({json: {user_content_id: id, status: 'saved'}});
    }
    if (url.pathname === '/api/my-contents') return route.fulfill({json: {items: [{
      content_id: 'fresh', title: 'New lesson', provider: 'youtube', content_type: 'video',
      status: 'saved', duration_seconds: 890, progress_ratio: 0, metadata_json: {},
    }], next_cursor: null, facets: {}}});
    if (url.pathname === '/api/plan-sessions' && route.request().method() === 'POST') {
      plans.push(route.request().postDataJSON());
      return route.fulfill({json: {id: 1}});
    }
    if (url.pathname === '/api/user') return route.fulfill({json: {user_id: 42, first_name: 'Javad', language: lang, timezone: 'Europe/Paris'}});
    return route.fulfill({json: {items: [], status: 'ok'}});
  });
  await page.goto(origin + path + '?lang=' + lang);
  return {page, plans, saves};
}

test('bookmarks stay filled after saving, filtering and reloading without removing cards', async t => {
  const {page, saves} = await openApp(t, '/explore');
  const existing = page.locator('article').filter({hasText: 'Already in Library'});
  await expect(existing.locator('.explore-card-quick-actions button')).toBeDisabled();
  await expect(existing.locator('.lucide-bookmark')).toHaveAttribute('fill', 'currentColor');
  const fresh = page.locator('article').filter({hasText: 'New lesson'});
  await fresh.locator('.explore-card-quick-actions button').click();
  await expect(fresh).toBeVisible();
  await expect(fresh.locator('.lucide-bookmark')).toHaveAttribute('fill', 'currentColor');
  await expect(fresh.getByRole('status')).toHaveText('Saved in Library');
  await page.locator('.explore-chips').getByRole('button', {name: 'Clubs', exact: true}).click();
  await page.locator('.explore-chips').getByRole('button', {name: 'Watch', exact: true}).click();
  await expect(fresh.locator('.explore-card-quick-actions button')).toBeDisabled();
  await page.reload();
  await expect(fresh.locator('.lucide-bookmark')).toHaveAttribute('fill', 'currentColor');
  assert.deepEqual(saves, ['fresh']);
});

test('custom suggestion remains in the future when the autumn clock repeats an hour', async t => {
  const {page, plans} = await openApp(t, '/my-contents', 'en', '2026-10-25T00:50:00Z');
  await page.locator('.content-card-quick-actions button').first().click();
  await page.locator('.plan-content-options > button').last().click();
  await expect(page.locator('input[type="datetime-local"]')).toHaveValue('2026-10-25T03:00');
  await page.locator('.plan-content-custom button').click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  assert.equal(plans[0].planned_start, '2026-10-25T02:00:00.000Z');
});

for (const lang of ['en', 'fa']) test('custom time is future, editable and confirmed explicitly: ' + lang, async t => {
  const {page, plans} = await openApp(t, '/my-contents', lang);
  await page.locator('.content-card-quick-actions button').first().click();
  await page.locator('.plan-content-options > button').last().click();
  const input = page.locator('input[type="datetime-local"]');
  await expect(input).toHaveValue('2026-10-03T00:30');
  assert.equal(plans.length, 0);
  await input.fill('2026-10-01T10:00');
  await page.locator('.plan-content-custom button').click();
  await expect(page.locator('.plan-content-error')).toBeVisible();
  assert.equal(plans.length, 0);
  await input.fill('2026-10-03T10:15');
  await page.locator('.plan-content-custom button').click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  assert.equal(plans.length, 1);
  assert.equal(plans[0].planned_start, '2026-10-03T08:15:00.000Z');
  assert.equal(plans[0].planned_duration_min, 15);
  await page.locator('.content-card-quick-actions button').first().click();
  await page.locator('.plan-content-options > button').last().click();
  await expect(input).toHaveValue('2026-10-03T00:30');
});
