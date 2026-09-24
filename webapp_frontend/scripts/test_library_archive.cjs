const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

const context = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/utils/libraryArchive.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, context);
const { restoredLibraryStatus } = context.exports;

test('restore preserves completed, partial and unwatched states', () => {
  assert.equal(restoredLibraryStatus({ progress_ratio: 1 }), 'completed');
  assert.equal(restoredLibraryStatus({ progress_ratio: .95 }), 'completed');
  assert.equal(restoredLibraryStatus({ progress_ratio: .35 }), 'in_progress');
  assert.equal(restoredLibraryStatus({ progress_ratio: 0 }), 'saved');
  assert.equal(restoredLibraryStatus({}), 'saved');
  assert.equal(restoredLibraryStatus({ progress_ratio: .1, completed_at: '2026-09-24' }), 'completed');
});

test('archive is visible and reversible, not a delete-only gesture', () => {
  const card = fs.readFileSync('src/components/ContentCard.tsx', 'utf8');
  assert.match(card, /className="content-card-archive-action"/);
  assert.match(card, /event\.stopPropagation\(\)/);
  assert.match(card, /disabled=\{updating\}/);
  assert.doesNotMatch(card, /Trash2|RemoveContentConfirmModal/);
  const page = fs.readFileSync('src/pages/MyContentsPage.tsx', 'utf8');
  assert.match(page, /key: 'archived', label: 'archived'/);
  assert.match(page, /onRestore=\{item.status === 'archived'/);
  assert.match(page, /restoredLibraryStatus\(item\)/);
  assert.match(page, /mutationInFlight\.current/);
  assert.doesNotMatch(page, /deleteContent|deleteUserContent/);
});

test('both languages include archive, restore and recovery guidance', () => {
  for (const language of ['en', 'fa']) {
    const strings = JSON.parse(fs.readFileSync(`src/i18n/locales/${language}.json`, 'utf8'));
    for (const key of ['archive', 'restoreToLibrary', 'archivedNotice', 'restoredNotice']) {
      assert.ok(strings.content[key]);
    }
    assert.ok(strings.myContents.status.archived);
  }
});
