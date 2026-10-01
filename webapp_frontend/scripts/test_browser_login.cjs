const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const source = fs.readFileSync('src/utils/browserLogin.ts', 'utf8');
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const context = { exports: {}, URL, URLSearchParams };
vm.runInNewContext(output, context);
const parse = context.exports.parseBrowserLoginCode;
const safeReturn = context.exports.safeLoginReturnTo;
const origin = 'https://xaana.club';
const code = 'A'.repeat(43);

test('accepts own fragment link or raw code', () => {
  assert.equal(parse(`${origin}/login#code=${code}`, origin), code);
  assert.equal(parse(` ${code} `, origin), code);
});

test('sign in preserves the shared video, club and language without credentials', () => {
  const target = '/youtube-watch?video_id=YSHZ9TMvNHc&content_id=item&club_id=club&lang=fa&ut=secret&start=30';
  assert.equal(safeReturn(target, origin), '/youtube-watch?video_id=YSHZ9TMvNHc&content_id=item&club_id=club&lang=fa&start=30');
  assert.equal(safeReturn('/pdf-reader?content_id=pdf&club_id=club', origin), '/pdf-reader?content_id=pdf&club_id=club');
  assert.equal(safeReturn('/plan-sessions/12/complete', origin), '/plan-sessions/12/complete');
  for (const target of ['//evil.example/youtube-watch?video_id=YSHZ9TMvNHc', '/\\evil.example',
    '/youtube-watch?video_id=bad', '/youtube-watch?video_id=YSHZ9TMvNHc#session_token=secret', '/admin', '/pdf-reader']) {
    assert.equal(safeReturn(target, origin), null);
  }
});
test('rejects foreign origins, query secrets, arbitrary paths and bad codes', () => {
  for (const input of [`https://evil.example/login#code=${code}`, `http://xaana.club/login#code=${code}`,
    `${origin}/dashboard#code=${code}`, `${origin}/login?code=${code}`, 'javascript:alert(1)', 'abc', '!'.repeat(43)]) {
    assert.equal(parse(input, origin), null);
  }
});
