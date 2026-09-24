// Run from the repository root: node --test tests/webapp/youtube_watch_startup.test.cjs
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium, expect} = require('../../webapp_frontend/node_modules/@playwright/test');
const html = fs.readFileSync('tm_bot/webapp/static/youtube_watch.html', 'utf8');
let browser;
before(async () => { browser = await chromium.launch({headless: true}); });
after(async () => { await browser?.close(); });

async function openViewer(t, options = {}) {
  const page = await browser.newPage({viewport: options.mobile ? {width: 390, height: 844} : {width: 1100, height: 850}});
  const errors = [], reports = [];
  let transcriptRequests = 0;
  page.on('pageerror', error => errors.push(error.message));
  t.after(async () => { await page.close(); assert.deepEqual(errors, []); });
  await page.clock.install({time: new Date('2026-09-24T12:00:00Z')});
  await page.clock.pauseAt(new Date('2026-09-24T12:00:01Z'));
  await page.addInitScript(() => localStorage.setItem('telegram_auth_token', 'test-session'));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/youtube-watch') return route.fulfill({contentType: 'text/html', body: html});
    if (url.pathname.endsWith('/progress')) {
      assert.equal(route.request().headers().authorization, 'Bearer test-session');
      if (options.progressGate) await options.progressGate;
      return route.fulfill({json: options.progress || {duration_seconds: 100, segments: [[0, 20], [50, 75]]}});
    }
    if (url.pathname.endsWith('/transcript')) {
      transcriptRequests++;
      const result = options.transcript ? options.transcript(transcriptRequests) : {available: false, status: 'unavailable'};
      return route.fulfill({status: result.httpStatus || 200, json: result});
    }
    if (url.pathname.endsWith('/report_stats')) {
      reports.push(route.request().postDataJSON().stats);
      return route.fulfill({json: {ok: true}});
    }
    if (url.hostname === 'xaana.test') return route.fulfill({json: {items: []}});
    // Never depend on YouTube, Telegram or a live account for this regression test.
    return route.fulfill({body: '', contentType: url.pathname.endsWith('.js') || url.pathname === '/iframe_api' ? 'application/javascript' : 'text/html'});
  });
  await page.goto('https://xaana.test/youtube-watch?video_id=du-G1B785Fs&content_id=item&lang=' + (options.lang || 'en'));
  return {page, reports, transcriptRequests: () => transcriptRequests};
}

async function installPlayer(page) {
  await page.evaluate(() => {
    window.testTime = 0;
    window.testState = 2;
    window.YT = {PlayerState: {PLAYING: 1, PAUSED: 2, ENDED: 0}, Player: function(id, config) {
      window.playerEvents = config.events;
      this.getCurrentTime = () => window.testTime;
      this.getPlayerState = () => window.testState;
      this.getDuration = () => 0; // metadata unavailable before playback
    }};
    window.onYouTubeIframeAPIReady();
    window.playerEvents.onReady();
  });
}

test('stored duration and coverage display before player readiness, including on reload', async t => {
  const {page, reports} = await openViewer(t);
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  await expect(page.locator('.progress-segment')).toHaveCount(2);
  await installPlayer(page);
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  await page.reload();
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  assert.equal(reports.length, 0);
});

test('unwatched video still displays an empty bar on a Persian mobile layout', async t => {
  const {page} = await openViewer(t, {mobile: true, lang: 'fa', progress: {duration_seconds: 100, segments: []}});
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  await expect(page.locator('#transcriptMessage')).toContainText('در دسترس نیست');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
});

test('pending subtitles turn into interactive cues without playing the video', async t => {
  const {page, transcriptRequests} = await openViewer(t, {transcript: n => n === 1
    ? {available: false, pending: true, status: 'pending'}
    : {available: true, language: 'fr', cues: [{start: 0, end: 2, text: 'Bonjour à tous'}]}});
  await expect(page.locator('#transcriptMessage')).toHaveText('Fetching subtitles…');
  await page.clock.runFor(10000);
  await expect(page.locator('.transcript-cue')).toHaveCount(1);
  await expect(page.locator('#transcriptStatus')).toBeHidden();
  assert.equal(transcriptRequests(), 2);
});

test('unavailable subtitles stop polling; transport failure offers a retry', async t => {
  const first = await openViewer(t);
  await expect(first.page.locator('#transcriptMessage')).toContainText('aren’t available');
  await first.page.clock.runFor(30000);
  assert.equal(first.transcriptRequests(), 1);
  const second = await openViewer(t, {transcript: n => n === 1 ? {httpStatus: 503} : {available: false, status: 'failed'}});
  await expect(second.page.getByRole('button', {name: 'Check again'})).toBeVisible();
  await second.page.getByRole('button', {name: 'Check again'}).click();
  await expect(second.page.locator('#transcriptMessage')).toContainText('couldn’t be loaded');
  await expect(second.page.locator('#transcriptRetry')).toBeHidden();
  assert.equal(second.transcriptRequests(), 2);
});

test('replays retain separate events and backward seeks leave unwatched gaps', async t => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const {page, reports} = await openViewer(t, {progressGate: gate, progress: {duration_seconds: 100, segments: [[80, 90]]}});
  await installPlayer(page);
  await page.evaluate(() => { window.testState = 1; window.playerEvents.onStateChange({data: 1}); });
  async function tick(time) {
    await page.evaluate(value => { window.testTime = value; }, time);
    await page.clock.runFor(1000);
  }
  for (let i = 0; i <= 6; i++) await tick(i);
  await tick(2); // replay within the first interval
  for (let i = 3; i <= 8; i++) await tick(i);
  await tick(50);
  for (let i = 51; i <= 55; i++) await tick(i);
  await tick(0); // backward seek across an unwatched gap
  for (let i = 1; i <= 3; i++) await tick(i);
  await page.evaluate(() => { window.testState = 2; window.playerEvents.onStateChange({data: 2}); });
  await expect.poll(() => reports.length).toBeGreaterThan(0);
  assert.deepEqual(reports.flatMap(report => report.segments), [[0, 6], [2, 8], [50, 55], [0, 3]]);
  release();
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '23');
  await expect(page.locator('.progress-segment')).toHaveCount(3);
  // Saved [80,90] is visible, but never sent again as newly watched time.
  assert.equal(reports.flatMap(report => report.segments).some(range => range[0] === 80), false);
});
