const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const context = { exports: {}, URLSearchParams };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/utils/exploreLearning.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, context);
const { starterEntries, videoDuration, youTubeUrlFor } = context.exports;

test('Explore defaults to videos, preserves explicit All, and clears subject on Clubs', () => {
  const { exploreFilter, exploreFilterParams } = context.exports;
  for (const value of [null, '', 'unknown']) assert.equal(exploreFilter(value), 'watch');
  for (const type of ['all', 'watch', 'decks', 'courses', 'habits', 'clubs']) {
    const params = exploreFilterParams(type, 'french');
    assert.equal(exploreFilter(params.get('type')), type);
    assert.equal(params.get('subject'), type === 'clubs' ? null : 'french');
  }
});

test('discovery opens practice details without enrolling; bookmark has an accessible label', () => {
  const card = fs.readFileSync('src/components/ExploreCard.tsx', 'utf8');
  assert.doesNotMatch(card, /joinChallenge|challengeIdFor/);
  assert.match(card, /learning\.viewCourse/);
  assert.match(card, /learning\.viewPractice/);
  assert.match(card, /learning\.setUpRoutine/);
  assert.match(card, /aria-label=\{t\(saveActionKey/);
  assert.match(card, /apiClient\.addUserContent/);
  assert.doesNotMatch(fs.readFileSync('src/pages/ExplorePage.tsx', 'utf8'), /listChallenges|joinChallenge/);
});

test('Today requires editorial eligibility AND cached captions in the subject language', () => {
  const items = [
    { id: 'ready', starter: true, subtitles_available: true, subtitle_language: 'fr-CA' },
    { id: 'translated', starter: true, subtitles_available: true, subtitle_language: 'en' },
    { id: 'uncached', starter: true, subtitles_available: false, subtitle_language: 'fr' },
    { id: 'not-curated', subtitles_available: true, subtitle_language: 'fr' },
    { id: 'unknown', starter: true, description: 'French subtitles!' },
  ];
  const catalog = { categories: [{ id: 'french', title: 'French', language: 'fr', topics: [{ id: 'watch', items }] }] };
  assert.equal(JSON.stringify(starterEntries(catalog).map(e => e.item.id)), '["ready"]');
  delete catalog.categories[0].language;
  assert.equal(starterEntries(catalog).length, 0);
});
test('duration hides unknown values and video links require a complete valid ID', () => {
  assert.equal(videoDuration(125), '2:05');
  for (const value of [null, undefined, 0, -1, NaN, Infinity]) assert.equal(videoDuration(value), null);
  assert.equal(youTubeUrlFor({ native_ref: '/youtube-watch?video_id=abcdefghijk&lang=en' }), 'https://www.youtube.com/watch?v=abcdefghijk');
  assert.equal(youTubeUrlFor({ native_ref: '/youtube-watch?video_id=abcdefghijkMORE' }), null);
});

test('Today mixes languages before repeats and falls back only to caption-ready picks', () => {
  const video = (id, language) => ({ id, starter: true, subtitles_available: true, subtitle_language: language });
  const french = [video('baguette', 'fr'), video('happiness', 'fr')];
  const english = [video('procrastination', 'en'), video('music', 'en')];
  const catalog = { categories: [
    { id: 'french', language: 'fr', topics: [{ id: 'watch', items: french }] },
    { id: 'english', language: 'en', topics: [{ id: 'watch', items: english }] },
  ] };
  const selected = () => JSON.stringify(starterEntries(catalog).slice(0, 2).map(entry => entry.item.id));
  assert.equal(selected(), '["baguette","procrastination"]');
  french[0].subtitles_available = false;
  assert.equal(selected(), '["happiness","procrastination"]');
  french[1].subtitle_language = 'en';
  assert.equal(selected(), '["procrastination","music"]');
  for (const item of english) item.subtitles_available = false;
  assert.equal(selected(), '[]');
});
test('main pages do not fetch or render people discovery', () => {
  const dashboard = fs.readFileSync('src/pages/DashboardPage.tsx', 'utf8');
  assert.doesNotMatch(dashboard, /getPublicUsers|community-sidebar|UserCard|SuggestionsInbox/);
  const navigation = fs.readFileSync('src/components/Navigation.tsx', 'utf8');
  assert.doesNotMatch(navigation, /key: 'community', label:/);
  const library = fs.readFileSync('src/pages/MyContentsPage.tsx', 'utf8');
  assert.doesNotMatch(library, /className="fab|className="content-library-decks"/);
  assert.match(library, /content-library-add-toggle/);
});

test('Explore keeps one scrollable filter row without repeating the header introduction', () => {
  const explore = fs.readFileSync('src/pages/ExplorePage.tsx', 'utf8');
  assert.doesNotMatch(explore, /explore-intro|learning\.exploreHint/);
  assert.match(explore, /select aria-label=\{t\('learning\.subject'\)\}/);
  assert.match(explore, /role="group" aria-label=\{t\('learning\.contentTypes'\)\}/);
  const css = fs.readFileSync('src/pages/explore.css', 'utf8');
  const bar = css.match(/\.explore-filter-bar\s*\{([^}]+)\}/)[1];
  assert.match(bar, /display: flex/);
  assert.match(bar, /flex-wrap: nowrap/);
  assert.match(bar, /overflow-x: auto/);
  assert.match(css, /\.explore-filter-bar \.explore-chips\s*\{[^}]*flex-wrap: nowrap/);
  assert.match(css, /\.explore-filter-bar \.explore-chip\s*\{[^}]*flex: 0 0 auto/);
});

const actionContext = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/utils/learningActions.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, actionContext);
const { saveActionKey, ROUTINE_EXAMPLES } = actionContext.exports;

test('video actions explicitly mean Library, never calendar scheduling or course membership', () => {
  assert.equal(saveActionKey(true, 'idle', false), 'learning.saveToLibrary');
  assert.equal(saveActionKey(true, 'adding', false), 'learning.savingToLibrary');
  assert.equal(saveActionKey(true, 'added', false), 'learning.savedToLibrary');
  assert.equal(saveActionKey(true, 'failed', false), 'learning.saveToLibrary');
  assert.equal(saveActionKey(false, 'idle', false), 'learning.join');
  assert.equal(saveActionKey(false, 'idle', true), 'learning.joined');
});

test('routine examples declare real weekly time budgets and only open an editable draft', () => {
  assert.equal(JSON.stringify(ROUTINE_EXAMPLES.map(example => example.id)), '["english","french"]');
  for (const example of ROUTINE_EXAMPLES) {
    assert.equal(example.hoursPerWeek * 60, example.minutes);
    assert.ok(example.hoursPerWeek > 0);
    for (const language of ['en', 'fa']) {
      const { learning } = JSON.parse(fs.readFileSync(`src/i18n/locales/${language}.json`, 'utf8'));
      assert.ok(learning.routines[example.id]);
      if (language === 'en') assert.match(learning.routines[example.id], /^Learn (English|French)$/);
    }
  }
  const start = fs.readFileSync('src/components/LearningStart.tsx', 'utf8');
  assert.doesNotMatch(start, /apiClient\.createPromise/);
  assert.match(start, /onCreateRoutine\(\{ text:/);
  assert.match(start, /text: t\(`learning\.routines\.\$\{example\.id\}`\)/);
  const modal = fs.readFileSync('src/components/CreatePromiseModal.tsx', 'utf8');
  assert.match(modal, /useState\(initialValues\?\.text/);
  assert.match(modal, /initialValues\?\.hoursPerWeek/);
  assert.match(modal, /useState<'private' \| 'public'>\('private'\)/);
});

test('profile menu keeps browser logout without the account-switch shortcut', () => {
  const navigation = fs.readFileSync('src/components/Navigation.tsx', 'utf8');
  assert.doesNotMatch(navigation, /accountSwitch\.title|UsersRound/);
  assert.match(navigation, /sessionMode === 'browser_token'/);
  assert.match(navigation, /onClick=\{handleLogout\}/);
  assert.match(fs.readFileSync('src/components/TelegramLogin.tsx', 'utf8'), /accountSwitch\.title/);
});
