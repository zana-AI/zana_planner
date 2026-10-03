// Offline UI checks: all APIs and external resources are mocked.
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium,expect}=require('@playwright/test');
const origin='http://127.0.0.1:5193';
let server,browser;
const catalog={version:1,categories:[
 {id:'french',title:'French',language:'fr',topics:[{id:'watch',title:'Watch',items:[
  {id:'one',content_id:'one',title:'French science',type:'video',order:1,native_ref:'/youtube-watch?video_id=abcdefghijk',tags:['science','technology']},
  {id:'two',title:'French news',type:'video',order:2,native_ref:'/youtube-watch?video_id=12345678901',tags:['news']},
  {id:'legacy',title:'Untagged story',type:'video',order:3,native_ref:'/youtube-watch?video_id=12345678902'},
 ]}]},
 {id:'english',title:'English',language:'en',topics:[{id:'watch',title:'Watch',items:[
  {id:'three',title:'English science',type:'video',order:1,native_ref:'/youtube-watch?video_id=12345678903',tags:['science']},
 ]}]},
]};
before(async()=>{
 server=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5193','--strictPort'],{stdio:'ignore'});
 for(let i=0;i<60;i++){try{if((await fetch(origin)).ok)break;}catch{}if(server.exitCode!==null)throw Error('Vite failed');await new Promise(r=>setTimeout(r,250));}
 browser=await chromium.launch({headless:true});
});
after(async()=>{await browser?.close();server?.kill();});
async function setup(t,lang='en'){
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],saves=[];
 page.on('pageerror',e=>errors.push(e.message));
 t.after(async()=>{await page.close();assert.deepEqual(errors,[]);});
 await page.addInitScript(()=>localStorage.setItem('telegram_auth_token','offline-test'));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.origin!==origin)return route.fulfill({body:'',contentType:'application/javascript'});
  if(url.pathname==='/api/explore')return route.fulfill({json:catalog});
  if(url.pathname==='/api/user-content'){saves.push(route.request().postDataJSON());return route.fulfill({json:{user_content_id:'saved'}});}
  if(url.pathname==='/api/user')return route.fulfill({json:{user_id:42,first_name:'Member',language:lang}});
  if(url.pathname.startsWith('/api/'))return route.fulfill({json:{items:[]}});
  return route.continue();
 });
 await page.goto(origin+'/explore?lang='+lang);
 await expect(page.locator('.explore-card')).toHaveCount(4);
 return {page,saves};
}
test('topic filters intersect language, retain URL state, and preserve bookmarks',async t=>{
 const {page,saves}=await setup(t);
 const topic=page.locator('.explore-tag-filter select');
 await topic.selectOption('science');
 await expect(page.locator('.explore-card')).toHaveCount(2);
 assert.equal(new URL(page.url()).searchParams.get('tag'),'science');
 await page.locator('.explore-filter-bar select').selectOption('french');
 await expect(page.locator('.explore-card')).toHaveCount(1);
 await expect(page.locator('.explore-card-title')).toHaveText('French science');
 await page.locator('.explore-card-quick-actions button').click();
 await expect(page.locator('.explore-card-quick-actions button')).toBeDisabled();
 assert.equal(saves.length,1);
 await page.goBack();await expect(page.locator('.explore-card')).toHaveCount(2);
 await page.goForward();await expect(page.locator('.explore-card')).toHaveCount(1);
 await topic.selectOption('all');await expect(page.locator('.explore-card')).toHaveCount(3);
 await page.screenshot({path:require('node:path').join(require('node:os').tmpdir(),'xaana-explore-topics-en.png'),fullPage:true});
});
test('Persian topic labels fit the mobile layout and untagged content remains visible',async t=>{
 const {page}=await setup(t,'fa');
 await expect(page.locator('.explore-tag-filter')).toContainText('موضوع');
 await expect(page.locator('.explore-content-tags').first()).toContainText('علم');
 await page.locator('.explore-tag-filter select').selectOption('news');
 await expect(page.locator('.explore-card')).toHaveCount(1);
 await expect(page.locator('.explore-card-title')).toHaveText('French news');
 await page.locator('.explore-tag-filter select').selectOption('all');
 await expect(page.locator('.explore-card')).toHaveCount(4);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
 await page.screenshot({path:require('node:path').join(require('node:os').tmpdir(),'xaana-explore-topics-fa.png'),fullPage:true});
});
