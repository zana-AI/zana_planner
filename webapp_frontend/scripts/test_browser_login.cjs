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
const origin = 'https://xaana.club';
const code = 'A'.repeat(43);

test('accepts own fragment link or raw code', () => {
  assert.equal(parse(`${origin}/login#code=${code}`, origin), code);
  assert.equal(parse(` ${code} `, origin), code);
});
test('rejects foreign origins, query secrets, arbitrary paths and bad codes', () => {
  for (const input of [`https://evil.example/login#code=${code}`, `http://xaana.club/login#code=${code}`,
    `${origin}/dashboard#code=${code}`, `${origin}/login?code=${code}`, 'javascript:alert(1)', 'abc', '!'.repeat(43)]) {
    assert.equal(parse(input, origin), null);
  }
});
