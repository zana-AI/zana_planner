from sqlalchemy import create_engine, text

from repositories.video_transcript_repo import fill_content_language_from_caption


def test_generated_caption_fills_only_missing_content_language():
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE content (provider TEXT, language TEXT, metadata_json TEXT)'))
        db.execute(text("INSERT INTO content VALUES ('youtube', NULL, '{\"video_id\":\"abcdefghijk\"}'), ('youtube', 'en', '{\"video_id\":\"abcdefghijk\"}')"))
        fill_content_language_from_caption(db, 'abcdefghijk', 'fr', True, 8)
        assert [row[0] for row in db.execute(text('SELECT language FROM content ORDER BY rowid'))] == ['fr', 'en']
        fill_content_language_from_caption(db, 'abcdefghijk', 'de', False, 8)
        assert [row[0] for row in db.execute(text('SELECT language FROM content ORDER BY rowid'))] == ['fr', 'en']
    engine.dispose()
