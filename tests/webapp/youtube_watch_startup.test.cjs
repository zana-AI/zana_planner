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
  const clubNotes = [];
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
    if (url.pathname.endsWith('/video-notes')) {
      return route.fulfill({json: {items: options.personalCards || []}});
    }
    if (options.club && url.pathname.endsWith('/club-video-words')) {
      assert.equal(url.searchParams.get('club_id'), 'club-1');
      return route.fulfill({json: {items: options.clubCards || []}});
    }
    if (options.club && url.pathname.endsWith('/club-video-progress')) {
      return route.fulfill({json: options.clubProgress || {duration_seconds: 100, items: [{user_id: '7', name: 'Marzieh', segments: [[5, 12]]}]}});
    }
    if (options.club && url.pathname.endsWith('/co-readers')) {
      assert.equal(url.searchParams.get('club_id'), 'club-1');
      assert.equal(route.request().headers().authorization, 'Bearer test-session');
      return route.fulfill({json: {items: [{user_id: '7', name: 'Marzieh', progress_ratio: 0.4}]}});
    }
    if (options.club && url.pathname.endsWith('/club-video-annotations')) {
      if (route.request().method() === 'POST') {
        assert.equal(route.request().postDataJSON().club_id, 'club-1');
        clubNotes.push({...route.request().postDataJSON(), id: 'note-1', author_name: 'You', is_mine: true});
      } else {
        assert.equal(url.searchParams.get('club_id'), 'club-1');
      }
      return route.fulfill({json: route.request().method() === 'POST' ? {annotation_id: 'note-1'} : {items: clubNotes}});
    }
    if (url.hostname === 'xaana.test') return route.fulfill({json: {items: []}});
    // Never depend on YouTube, Telegram or a live account for this regression test.
    return route.fulfill({body: '', contentType: url.pathname.endsWith('.js') || url.pathname === '/iframe_api' ? 'application/javascript' : 'text/html'});
  });
  await page.goto('https://xaana.test/youtube-watch?video_id=du-G1B785Fs&content_id=item&lang=' + (options.lang || 'en') + (options.club ? '&club_id=club-1' : ''));
  return {page, reports, transcriptRequests: () => transcriptRequests};
}

test('club video shows member progress and saves a timestamped note', async t => {
  const {page} = await openViewer(t, {club: true});
  await expect(page.locator('#clubActivity')).toBeVisible();
  await expect(page.locator('#clubReaderList')).toContainText('Marzieh');
  await page.locator('#clubActivity summary').click();
  await installPlayer(page);
  await page.evaluate(() => { window.testTime = 42; });
  await page.locator('#clubNoteBody').fill('This phrase is useful');
  await page.locator('#clubNoteSubmit').click();
  await expect(page.locator('#clubNoteList')).toContainText('This phrase is useful');
  await expect(page.locator('#clubNoteList')).toContainText('0:42');
});

test('club video shows each member card with a decorative creator circle', async t => {
  const {page} = await openViewer(t, {club: true,
    personalCards: [{note_id: 'mine', front: 'voyager', back: 'travel', deck_id: 'my-deck', deck_name: 'French'}],
    clubCards: [
      {note_id: 'mine', user_id: '7', creator_name: 'You', front: 'voyager', back: 'travel', start: 3, is_mine: true},
      {note_id: 'peer', user_id: '8', creator_name: 'Marzieh', front: 'partir', back: 'leave', start: 5, is_mine: false},
    ],
  });
  await expect(page.locator('#savedWords')).toBeVisible();
  await expect(page.locator('.saved-card')).toHaveCount(2);
  await expect(page.locator('.saved-creator')).toHaveCount(2);
  assert.equal(await page.locator('.saved-creator').first().evaluate(el => el.tagName), 'SPAN');
  await expect(page.locator('#savedReview')).toBeVisible();
  await expect(page.locator('#savedList')).toContainText('partir');
  assert.equal(await page.locator('.saved-creator').last().getAttribute('aria-label'), 'Saved by Marzieh');
});

test('peer cards do not provide a review link and progress rows open profiles', async t => {
  const {page} = await openViewer(t, {club: true,
    clubCards: [{note_id: 'peer', user_id: '8', creator_name: 'Marzieh', front: 'partir', back: 'leave'}],
    clubProgress: {duration_seconds: 100, items: [{user_id: '8', name: 'Marzieh', segments: [[5, 12]]}]},
  });
  await expect(page.locator('#savedWords')).toBeVisible();
  await expect(page.locator('#savedReview')).toBeHidden();
  await page.locator('#clubActivity summary').click();
  await expect(page.locator('#clubReaderList .club-reader-person')).toBeVisible();
  await page.locator('#clubReaderList .club-reader-person').click();
  await expect(page).toHaveURL(/\/users\/8$/);
});

async function installPlayer(page) {
  await page.evaluate(() => {
    window.testTime = 0;
    window.testState = 2;
    window.seekCalls = [];
    window.playCalls = 0;
    window.YT = {PlayerState: {PLAYING: 1, PAUSED: 2, ENDED: 0}, Player: function(id, config) {
      window.playerEvents = config.events;
      this.getCurrentTime = () => window.testTime;
      this.getPlayerState = () => window.testState;
      this.getDuration = () => 0; // metadata unavailable before playback
      this.seekTo = seconds => { window.seekCalls.push(seconds); };
      this.playVideo = () => { window.playCalls++; };
    }};
    window.onYouTubeIframeAPIReady();
    window.playerEvents.onReady();
  });
}

test('stored duration and coverage display before player readiness, including on reload', async t => {
  const {page, reports} = await openViewer(t);
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  await expect(page.locator('.progress-segment')).toHaveCount(2);
  const resume = page.getByRole('button', {name: /Jump to furthest watched point/});
  await expect(resume).toBeDisabled();
  await installPlayer(page);
  await expect(resume).toBeEnabled();
  await resume.click();
  assert.deepEqual(await page.evaluate(() => window.seekCalls), [75]);
  assert.equal(await page.evaluate(() => window.playCalls), 1);
  await page.locator('#transcriptTitle').click();
  await expect(page.locator('#transcript')).not.toHaveAttribute('open', '');
  await expect(resume).toBeVisible();
  const settings = page.getByRole('button', {name: 'Transcript settings'});
  await expect(settings).toBeVisible();
  await resume.click();
  assert.deepEqual(await page.evaluate(() => window.seekCalls), [75, 75]);
  await settings.click();
  await expect(page.locator('#transcript')).toHaveAttribute('open', '');
  await expect(page.getByRole('slider', {name: 'Transcript text size'})).toBeVisible();
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  await page.reload();
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  assert.equal(reports.length, 0);
});

test('Persian watch header matches the reader bar with a left back button', async t => {
  const {page} = await openViewer(t, {mobile: true, lang: 'fa'});
  const layout = await page.evaluate(() => {
    const title = document.getElementById('videoTitle');
    title.textContent = 'AMD Acquires World Labs';
    title.hidden = false;
    const back = document.getElementById('backBtn').getBoundingClientRect();
    const heading = title.getBoundingClientRect();
    const bar = document.querySelector('.watch-header');
    return {
      backLeft: back.left,
      titleLeft: heading.left,
      direction: getComputedStyle(bar).direction,
      titleSize: getComputedStyle(title).fontSize,
      barHeight: bar.getBoundingClientRect().height,
      barLeft: bar.getBoundingClientRect().left,
      barWidth: bar.getBoundingClientRect().width
    };
  });
  assert.ok(layout.backLeft < layout.titleLeft);
  assert.equal(layout.direction, 'ltr');
  assert.equal(layout.titleSize, '13px');
  assert.equal(layout.barHeight, 48);
  assert.equal(layout.barLeft, 0);
  assert.equal(layout.barWidth, 390);
});

test('unwatched video still displays an empty bar on a Persian mobile layout', async t => {
  const {page} = await openViewer(t, {mobile: true, lang: 'fa', progress: {duration_seconds: 100, segments: []}});
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  await expect(page.locator('#resumeWatched')).toBeHidden();
  await expect(page.locator('#transcriptMessage')).toContainText('زیرنویسی پیدا نشد');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
});

test('fully watched video resumes at its last playable second', async t => {
  const {page} = await openViewer(t, {progress: {duration_seconds: 100, segments: [[0, 100]]}});
  await installPlayer(page);
  await page.getByRole('button', {name: /Jump to furthest watched point/}).click();
  assert.deepEqual(await page.evaluate(() => window.seekCalls), [99]);
});

test('transcript text size persists on this device without closing the panel', async t => {
  const {page} = await openViewer(t, {mobile: true, lang: 'fa', transcript: () => ({
    available: true, language: 'fr', source: 'automatic', cues: [{start: 0, end: 2, text: 'Bonjour à tous'}]
  })});
  const settings = page.getByRole('button', {name: 'تنظیمات زیرنویس'});
  const slider = page.getByRole('slider', {name: 'اندازهٔ متن زیرنویس'});
  const cueText = page.locator('.transcript-text');
  await expect(cueText).toHaveCSS('font-size', '13px');
  await expect(slider).toBeHidden();
  assert.equal(await page.evaluate(() => {
    const title = document.getElementById('transcriptTitle');
    const titleText = document.createRange();
    titleText.selectNodeContents(title);
    const titleBounds = titleText.getBoundingClientRect();
    const controlsBounds = document.querySelector('.transcript-header-actions').getBoundingClientRect();
    return titleBounds.left >= controlsBounds.right;
  }), true);
  await settings.click();
  await expect(slider).toBeVisible();
  await expect(settings).toHaveAttribute('aria-expanded', 'true');
  await slider.focus();
  await slider.press('End');
  await expect(slider).toHaveValue('28');
  await expect(cueText).toHaveCSS('font-size', '28px');
  await expect(page.locator('#transcript')).toHaveAttribute('open', '');
  assert.equal(await page.evaluate(() => localStorage.getItem('xaana-transcript-font-size')), '28');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.setViewportSize({width: 320, height: 844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.reload();
  await settings.click();
  await expect(slider).toHaveValue('28');
  await expect(cueText).toHaveCSS('font-size', '28px');
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
  await expect(page.getByRole('button', {name: /Jump to furthest watched point/})).toBeEnabled();
  await expect(page.locator('.progress-segment')).toHaveCount(3);
  // Saved [80,90] is visible, but never sent again as newly watched time.
  assert.equal(reports.flatMap(report => report.segments).some(range => range[0] === 80), false);
});
