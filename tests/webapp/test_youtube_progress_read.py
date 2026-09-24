"""Exercise the startup read query with real rows, including other users/items."""
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from repositories import youtube_progress_repo as module


def test_startup_coverage_reads_only_this_users_video_seconds(monkeypatch):
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('''CREATE TABLE content_consumption_event (
            user_id text, content_id text, position_unit text,
            start_position float, end_position float)'''))
        connection.execute(text('''INSERT INTO content_consumption_event VALUES
            ('42','item','seconds',0,20), ('42','item','seconds',10,30),
            ('42','item','seconds',80,120), ('other','item','seconds',0,100),
            ('42','other','seconds',0,100), ('42','item','ratio',0,1)'''))

    @contextmanager
    def use_session():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(module, 'get_db_session', use_session)
    repo = module.YoutubeProgressRepository()
    assert repo.get_progress(42, 'item', 100) == {
        'duration_seconds': 100, 'segments': [[0, 30], [80, 100]]}
    assert repo.get_progress(42, 'item', None)['segments'] == [[0, 30], [80, 120]]
    assert repo.get_progress(42, 'unwatched', 100)['segments'] == []
    with engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM content_consumption_event')).scalar() == 6
    engine.dispose()
