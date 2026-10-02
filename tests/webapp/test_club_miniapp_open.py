import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlencode, urlparse, parse_qs
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from webapp.routers.auth import router
from repositories.content_share_repo import ContentShareRepository
from repositories.content_repo import ContentRepository
from services.content_share_service import club_miniapp_url, club_open_keyboard

TOKEN='offline-token'
CID='83dedd7d-7e1b-4925-b2f7-f8e4a25f8b6f'
CLUB='477376d8-dc2a-4cfb-a048-e3d1f8381a9c'

@pytest.fixture
def setup(monkeypatch):
    member=Mock(return_value=True)
    monkeypatch.setattr(ContentShareRepository,'is_active_member_of_share',member)
    content=Mock(return_value={'id':CID,'provider':'youtube','original_url':'https://youtu.be/YSHZ9TMvNHc','metadata_json':{}})
    monkeypatch.setattr(ContentRepository,'get_content_by_id',content)
    app=FastAPI(); app.include_router(router); app.state.bot_token=TOKEN
    repo=Mock(); repo.create_session.return_value=SimpleNamespace(session_token='test-session')
    app.state.auth_session_repo=repo
    with TestClient(app) as http: yield http,repo,member,content

def signed(uid=42, age=0):
    data={'auth_date':str(int(time.time())-age),'user':json.dumps({'id':uid,'first_name':'Member'}), 'start_param':'clubread_'+CID.replace('-','')+'_'+CLUB.replace('-','')}
    check='\n'.join(f'{key}={value}' for key,value in sorted(data.items()))
    secret=hmac.new(b'WebAppData',TOKEN.encode(),hashlib.sha256).digest()
    data['hash']=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
    return urlencode(data)

def post(http, data=None, **body):
    return http.post('/api/auth/club-miniapp-open',json={'content_id':CID,'club_id':CLUB,'language':'fa',**body},headers={'X-Telegram-Init-Data':data if data is not None else signed(), 'Authorization':'Bearer previous-account'})

def test_current_telegram_member_and_exact_video_context(setup):
    http,repo,member,_=setup
    for uid in [42,99]:
        r=post(http,signed(uid))
        assert r.status_code==200
        assert r.headers['cache-control']=='no-store'
        path=urlparse(r.json()['path']); query=parse_qs(path.query)
        assert path.path=='/youtube-watch'
        assert query=={'video_id':['YSHZ9TMvNHc'],'content_id':[CID],'club_id':[CLUB],'lang':['fa']}
        member.assert_called_with(CID,CLUB,str(uid))
        assert repo.create_session.call_args.kwargs=={'user_id':uid,'telegram_auth_date':int(parse_qs(signed(uid))['auth_date'][0]),'expires_in_days':1,'auth_method':'miniapp'}
    repo.get_session.assert_not_called()

@pytest.mark.parametrize('data',[ '', 'user=%7B%22id%22%3A42%7D', signed(age=86401), signed(age=-120), signed(uid=-1)])
def test_no_unsigned_expired_or_browser_identity_can_mint_session(setup,data):
    http,repo,member,_=setup
    assert post(http,data).status_code==401
    repo.create_session.assert_not_called(); member.assert_not_called()

def test_non_member_or_revoked_share_is_denied(setup):
    http,repo,member,_=setup; member.return_value=False
    assert post(http).status_code==403
    repo.create_session.assert_not_called()

def test_pdf_handoff(setup):
    http,_,_,content=setup; content.return_value={'id':CID,'provider':'telegram_pdf','metadata_json':{}}
    assert post(http).json()['path']==f'/pdf-reader?content_id={CID}&club_id={CLUB}&lang=fa'

def test_external_content_cannot_receive_session(setup):
    http,repo,_,content=setup; content.return_value={'id':CID,'provider':'web','canonical_url':'https://example.org','metadata_json':{}}
    assert post(http).status_code==400
    repo.create_session.assert_not_called()

def test_public_button_is_destination_only_and_rollout_is_gated(monkeypatch):
    monkeypatch.delenv('CLUB_MINIAPP_LINKS_ENABLED',raising=False)
    path=f'/youtube-watch?content_id={CID}&club_id={CLUB}'
    assert 'login_url' in club_open_keyboard(path,'Open')['inline_keyboard'][0][0]
    link=club_miniapp_url(CID,CLUB,'xaana_bot')
    assert link==f'https://t.me/xaana_bot?startapp=clubread_{CID.replace("-", "")}_{CLUB.replace("-", "")}'
    assert len(parse_qs(urlparse(link).query)['startapp'][0])<512
    monkeypatch.setenv('CLUB_MINIAPP_LINKS_ENABLED','1'); monkeypatch.setenv('TELEGRAM_BOT_USERNAME','xaana_bot')
    assert club_open_keyboard(path,'Open')['inline_keyboard'][0][0]=={'text':'Open','url':link}
