const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

const context = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/utils/promisePace.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, context);
const { getPromisePaceStatus } = context.exports;
const week = ['2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01',
  '2026-10-02', '2026-10-03', '2026-10-04'];
const midday = (day) => new Date(`${day}T12:00:00`);

test('pace allows work during the current day and compares unrounded progress', () => {
  assert.equal(getPromisePaceStatus(0, 7, week, midday('2026-09-28')).key, 'onTrack');
  assert.equal(getPromisePaceStatus(1, 7, week, midday('2026-09-29')).key, 'onTrack');
  assert.equal(getPromisePaceStatus(1, 2, week, midday('2026-09-29')).key, 'onTrack');
});

test('at-risk status always carries the red class, including zero progress', () => {
  const status = getPromisePaceStatus(0, 1, week, midday('2026-09-29'));
  assert.equal(status.key, 'atRisk');
  assert.equal(status.cls, 'bad');
  assert.equal(getPromisePaceStatus(0, 7, week, midday('2026-09-27')).key, 'onTrack');
  assert.equal(getPromisePaceStatus(0, 7, week, midday('2026-10-05')).key, 'atRisk');
});
