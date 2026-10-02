// From webapp_frontend: node --test scripts/test_club_miniapp_launch.cjs
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const {chromium,expect}=require('@playwright/test');
const origin='http://127.0.0.1:5192';
const cid='83dedd7d-7e1b-4925-b2f7-f8e4a25f8b6f', club='477376d8-dc2a-4cfb-a048-e3d1f8381a9c';
const start='clubread_'+cid.replaceAll('-','')+'_'+club.replaceAll('-','');
const viewer=fs.readFileSync('../tm_bot/webapp/static/youtube_watch.html','utf8');
let server,browser;
before(async()=>{
 server=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5192','--strictPort'],{stdio:'ignore'});
 for(let i=0;i<60;i++){try{if((await fetch(origin)).ok)break;}catch{} if(server.exitCode!==null)throw Error('Vite failed');await new Promise(r=>setTimeout(r,250));}
 browser=await chromium.launch({headless:true});
});
after(async()=>{await browser?.close();server?.kill();});
async function launch(t,options={}){
 const page=await browser.newPage({viewport:{width:390,height:844}}), opens=[], errors=[], requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('popup',()=>opens.push('popup'));
 t.after(async()=>{await page.close();assert.deepEqual(errors,[]);assert.deepEqual(opens,[]);});
 await page.addInitScript(({start,guest})=>{
  localStorage.setItem('telegram_auth_token','old-browser-account');
  if(!guest)window.Telegram={WebApp:{initData:'signed-current-member',initDataUnsafe:{start_param:start,user:{id:42,first_name:'Member',language_code:'fa'}},ready(){},expand(){},MainButton:{hide(){}},onEvent(){}}};
 },{start,guest:!!options.guest});
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.origin!==origin)return route.fulfill({body:'',contentType:'application/javascript'});
  if(url.pathname==='/youtube-watch')return route.fulfill({contentType:'text/html',body:viewer});
  if(url.pathname==='/pdf-reader')return route.fulfill({contentType:'text/html',body:'<h1>PDF reader destination</h1>'});
  if(url.pathname==='/api/auth/club-miniapp-open'){
   assert.equal(route.request().headers()['x-telegram-init-data'],'signed-current-member');
   assert.equal(route.request().headers().authorization,undefined);
   requests.push(route.request().postDataJSON());
   if(options.deny)return route.fulfill({status:403,json:{detail:'Revoked share'}});
   const path=options.pdf?`/pdf-reader?content_id=${cid}&club_id=${club}&lang=fa`:`/youtube-watch?video_id=YSHZ9TMvNHc&content_id=${cid}&club_id=${club}&lang=fa`;
   return route.fulfill({json:{path,session_token:'current-member-session'}});
  }
  if(url.pathname.endsWith('/progress'))return route.fulfill({json:{duration_seconds:100,segments:[]}});
  if(url.pathname.endsWith('/transcript'))return route.fulfill({json:{available:false,status:'unavailable'}});
  if(url.pathname==='/api/user')return route.fulfill({json:{user_id:42,first_name:'Member',language:'fa'}});
  if(url.pathname==='/api/my-contents')return route.fulfill({json:{items:[],facets:{}}});
  if(url.pathname.startsWith('/api/'))return route.fulfill({json:{items:[],status:'ok'}});
  return route.continue();
 });
 await page.goto(origin+'/?tgWebAppStartParam='+start+'&lang=fa');
 return {page,requests};
}
test('Mini App opens exact club video in the same browser and Back does not replay launch',async t=>{
 const {page,requests}=await launch(t);
 await expect(page).toHaveURL(/\/youtube-watch\?/);
 await expect(page.locator('#watchAuthNotice')).toBeHidden();
 const url=new URL(page.url());assert.equal(url.origin,origin);assert.equal(url.hash,'');
 assert.equal(url.searchParams.get('club_id'),club);assert.equal(url.searchParams.get('content_id'),cid);
 assert.deepEqual(requests,[{content_id:cid,club_id:club,language:'fa'}]);
 assert.equal(await page.evaluate(()=>localStorage.getItem('telegram_auth_token')),'current-member-session');
 await page.locator('#backBtn').click();
 await expect(page).toHaveURL(/\/my-contents$/);
 await expect(page.locator('.content-library-page')).toBeVisible();
 assert.equal(requests.length,1);
});
test('PDF launch retains its content and club destination',async t=>{
 const {page,requests}=await launch(t,{pdf:true});
 await expect(page.getByRole('heading',{name:'PDF reader destination'})).toBeVisible();
 assert.equal(new URL(page.url()).searchParams.get('club_id'),club);assert.equal(requests.length,1);
});
test('ordinary browser account cannot stand in for Telegram identity',async t=>{
 const {page,requests}=await launch(t,{guest:true});
 await expect(page.getByRole('alert')).toBeVisible();assert.equal(requests.length,0);
 assert.equal(new URL(page.url()).pathname,'/');
});
test('revoked club access shows an error without opening content',async t=>{
 const {page,requests}=await launch(t,{deny:true});
 await expect(page.getByRole('alert')).toBeVisible();assert.equal(requests.length,1);
 assert.equal(new URL(page.url()).pathname,'/');
});
