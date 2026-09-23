const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const html = fs.readFileSync('tm_bot/webapp/static/youtube_watch.html', 'utf8');
const block = html.slice(html.indexOf('  var watchOutbox ='), html.indexOf('  // WATCH_REPORT_OUTBOX_END'));
function setup(send, storage=new Map()) {
  let token = 'account-A';
  let pending = {stats:{report_id:'stable-id',segments:[[0,30]]}};
  const ctx = vm.createContext({crypto:webcrypto,TextEncoder,Uint8Array,AbortController,setTimeout,clearTimeout,
    authHeaders:()=>({'Authorization':'Bearer '+token}),userToken:'',videoId:'du-G1B785Fs',contentId:'item',
    baseUrl:'https://xaana.club',uiLanguage:'en',window:{},document:{getElementById:()=>({})},
    sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},fetch:send,
    takeStatsPayload:()=>{const value=pending;pending=null;return value;}});
  vm.runInContext(block, ctx);
  return {ctx,storage,changeAccount:()=>{token='account-B';}, add:()=>{pending={stats:{report_id:'second',segments:[[30,60]]}};}};
}
test('401/network failures retain the same report; only acknowledgement removes it', async()=>{
  const bodies=[];let attempts=0;
  const h=setup(async(url,opt)=>{
    assert.equal(opt.headers.Authorization,'Bearer account-A');
    bodies.push(JSON.parse(opt.body));
    return {ok:++attempts>1,json:async()=>({ok:true})};
  });
  assert.equal(await h.ctx.flushStats('pause'),false);
  assert.equal(h.ctx.watchOutbox.length,1);
  assert.equal(await h.ctx.flushStats('retry'),true);
  assert.equal(h.ctx.watchOutbox.length,0);
  assert.deepEqual(bodies[0].stats,bodies[1].stats);
  assert(![...h.storage.values()].join('').includes('account-A'));
});
test('overlapping flushes serialize and send new ranges once',async()=>{
  let release;const calls=[];
  const h=setup(async(url,opt)=>{calls.push(JSON.parse(opt.body).stats.report_id);if(calls.length===1)await new Promise(r=>release=r);return {ok:true,json:async()=>({ok:true})};});
  const first=h.ctx.flushStats('interval');
  await new Promise(r=>setTimeout(r,20));h.add();const second=h.ctx.flushStats('pause');
  release();await Promise.all([first,second]);
  assert.deepEqual(calls,['stable-id','second']);
});
test('account switch cannot replay the previous account queue',async()=>{
  let calls=0;const h=setup(async()=>{calls++;throw Error('offline');});
  await h.ctx.flushStats('pause');h.changeAccount();
  assert.equal(await h.ctx.flushStats('retry'),false);assert.equal(calls,1);
});
test('reload recovers unacknowledged reports from session storage',async()=>{
  const first=setup(async()=>{throw Error('offline');});await first.ctx.flushStats('pause');
  const sent=[];const second=setup(async(url,opt)=>{sent.push(JSON.parse(opt.body).stats.report_id);return {ok:true,json:async()=>({ok:true})};},first.storage);
  // Do not simulate a second newly watched range on reload.
  second.ctx.takeStatsPayload=()=>null;
  assert.equal(await second.ctx.flushStats('retry'),true);assert.deepEqual(sent,['stable-id']);
});
