"""Archive/restore touches only the user's shelf state, never learning data."""
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text

from repositories import content_repo


@pytest.fixture
def archive_db(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('''CREATE TABLE user_content (
            user_id TEXT, content_id TEXT, status TEXT, notes TEXT, rating INTEGER,
            progress_ratio REAL, last_position REAL, position_unit TEXT,
            last_interaction_at TEXT, total_consumed_seconds REAL, completed_at TEXT
        )'''))
        connection.execute(text('''CREATE TABLE content (
            id TEXT, content_type TEXT, provider TEXT, metadata_json TEXT
        )'''))
        connection.execute(text("INSERT INTO content VALUES ('v', 'video', 'youtube', '{}'), ('p', 'text', 'telegram_pdf', '{}')"))
        connection.execute(text('''INSERT INTO user_content VALUES
            ('42', 'v', 'completed', 'my notes', 5, 1, 120, 'seconds', 'before', 120, 'finished'),
            ('other', 'v', 'saved', NULL, NULL, 0, 0, 'seconds', NULL, 0, NULL),
            ('42', 'p', 'archived', NULL, NULL, .3, .3, 'ratio', NULL, 30, NULL)
        '''))

    @contextmanager
    def session():
        with engine.begin() as connection:
            yield connection

    monkeypatch.setattr(content_repo, 'get_db_session', session)
    yield engine, content_repo.ContentRepository()
    engine.dispose()


def row(engine, user='42', content='v'):
    with engine.connect() as connection:
        return dict(connection.execute(text(
            'SELECT * FROM user_content WHERE user_id=:user AND content_id=:content'
        ), {'user': user, 'content': content}).mappings().one())


def test_archive_restore_preserves_progress_notes_rating_and_other_user(archive_db):
    engine, repo = archive_db
    before = row(engine)
    other_before = row(engine, user='other')
    repo.update_user_content_meta('42', 'v', status='archived')
    assert row(engine) == {**before, 'status': 'archived'}
    assert row(engine, user='other') == other_before
    repo.update_user_content_meta('42', 'v', status='completed')
    assert row(engine) == before


def test_late_progress_does_not_unarchive(archive_db):
    engine, repo = archive_db
    repo.update_user_content_progress('42', 'p', progress_ratio=.5, status='in_progress', last_position=.5)
    saved = row(engine, content='p')
    assert saved['status'] == 'archived'
    assert saved['progress_ratio'] == .5
    assert saved['last_position'] == .5


def test_status_facets_include_archive_but_main_library_type_counts_do_not(archive_db):
    _, repo = archive_db
    default = repo.get_user_content_facets('42')
    assert default == {'status': {'completed': 1, 'archived': 1}, 'content_type': {'video': 1}}
    archived = repo.get_user_content_facets('42', status='archived')
    assert archived['status'] == default['status']
    assert archived['content_type'] == {'pdf': 1}
    assert repo.get_user_content_facets('42', status='saved')['content_type'] == {}
