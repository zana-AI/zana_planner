"""Only hashes of high-entropy pairing codes/device tokens are stored."""
import hashlib
import secrets
import uuid

from sqlalchemy import text
from db.postgres_db import get_db_session


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class CaptionRelayRepository:
    def create(self, name, admin_id):
        code, device_id = secrets.token_urlsafe(32), str(uuid.uuid4())
        with get_db_session() as session:
            session.execute(text("""
                INSERT INTO caption_relay_devices (id,name,created_by,pairing_hash,pairing_expires_at)
                VALUES (:id,:name,:admin,:hash,now()+interval '10 minutes')
            """), {"id": device_id, "name": name, "admin": str(admin_id), "hash": digest(code)})
        return {"id": device_id, "pairing_code": code, "expires_in": 600}

    def pair(self, code):
        token = "xcr_" + secrets.token_urlsafe(32)
        with get_db_session() as session:
            row = session.execute(text("""
                UPDATE caption_relay_devices SET token_hash=:token, pairing_hash=NULL,
                    pairing_expires_at=NULL, activated_at=now()
                WHERE pairing_hash=:code AND pairing_expires_at>now() AND revoked_at IS NULL
                AND token_hash IS NULL RETURNING id,name
            """), {"token": digest(token), "code": digest(code)}).mappings().first()
            if not row:
                return None
            return {"device_id": row["id"], "name": row["name"], "token": token}

    def authenticate(self, token):
        if not token.startswith("xcr_") or len(token) != 47:
            return None
        with get_db_session() as session:
            return session.execute(text("""
                SELECT id FROM caption_relay_devices WHERE token_hash=:hash AND revoked_at IS NULL
            """), {"hash": digest(token)}).scalar()

    def list_devices(self):
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT id,name,created_at,activated_at,revoked_at,last_seen_at,pairing_expires_at
                FROM caption_relay_devices ORDER BY created_at DESC LIMIT 100
            """)).mappings().all()
            jobs = session.execute(text("""
                SELECT fetch_stage,status,count(*) AS count FROM video_transcript_fetch_jobs GROUP BY 1,2
            """)).mappings().all()
            return {"devices": [dict(r) for r in rows], "queue": [dict(r) for r in jobs]}

    def revoke(self, device_id):
        with get_db_session() as session:
            session.execute(text("""
                UPDATE caption_relay_devices SET revoked_at=now(),token_hash=NULL,pairing_hash=NULL WHERE id=:id
            """), {"id": device_id})
            session.execute(text("""
                UPDATE video_transcript_fetch_jobs SET status='queued',lease_token=NULL,leased_until=NULL,
                    worker_id=NULL,available_at=now() WHERE worker_id=:id AND status='processing'
            """), {"id": device_id})
