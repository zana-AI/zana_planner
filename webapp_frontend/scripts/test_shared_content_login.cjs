// From webapp_frontend: node --test scripts/test_shared_content_login.cjs
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const {chromium, expect} = require('@playwright/test');
const origin = 'http://127.0.0.1:5186';
const destination = '/youtube-watch?video_id=YSHZ9TMvNHc&content_id=item&club_id=club&lang=fa';
const html = fs.readFileSync('../tm_bot/webapp/static/youtube_watch.html', 'utf8');
let server, browser;
before(async () => {
  server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5186', '--strictPort'], {stdio: 'ignore'});
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(origin)).ok) break; } catch {}
    if (server.exitCode !== null) throw new Error('Vite failed to start');
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  browser = await chromium.launch({headless:true});
});
after(async () => { await browser?.close(); server?.kill(); });

async function loginPage(t) {
  const page = await browser.newPage();
  t.after(() => page.close());
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.fulfill({body:'',contentType:'application/javascript'});
    if (url.pathname === '/youtube-watch') return route.fulfill({body:html,contentType:'text/html'});
    if (url.pathname === '/api/auth/bot-username') return route.fulfill({json:{bot_username:'xaana_bot'}});
    if (url.pathname === '/api/auth/browser-login/preview') return route.fulfill({json:{user_id:'42',first_name:'Akram',username:'AA'}});
    if (url.pathname === '/api/auth/browser-login/redeem' || url.pathname === '/api/auth/telegram-login') return route.fulfill({json:{session_token:'verified-session'}});
    if (url.pathname.endsWith('/progress')) {
      assert.equal(route.request().headers().authorization, 'Bearer verified-session');
      return route.fulfill({json:{duration_seconds:736,segments:[]}});
    }
    if (url.pathname.startsWith('/api/')) return route.fulfill({json:{items:[]}});
    return route.continue();
  });
  return page;
}

test('Telegram browser login returns to the same shared video', async t => {
  const page = await loginPage(t);
  await page.goto(`${origin}/login?return_to=${encodeURIComponent(destination)}`);
  await expect.poll(() => page.evaluate(() => typeof window.onTelegramAuth)).toBe('function');
  await page.evaluate(() => window.onTelegramAuth({id:42}));
  await expect(page).toHaveURL(origin + destination);
  await expect(page.locator('#watchAuthNotice')).toBeHidden();
});

test('the one-use bot login fallback also returns to the shared video', async t => {
  const page = await loginPage(t);
  await page.goto(`${origin}/login?return_to=${encodeURIComponent(destination)}`);
  await expect(page.getByRole('heading', {level:1})).toBeVisible();
  await page.goto(`${origin}/login#code=${'A'.repeat(43)}`);
  await expect(page.getByRole('heading', {name:'Akram'})).toBeVisible();
  await page.locator('.browser-login-confirm button').click();
  await expect(page).toHaveURL(origin + destination);
  await expect(page.locator('#watchAuthNotice')).toBeHidden();
});
