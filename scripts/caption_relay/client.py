"""Xaana Caption Relay. HTTPS only; no SQL, SSH, app login or shell commands."""
import argparse
import getpass
import json
import logging
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

LOG = logging.getLogger("xaana-caption-relay")
DEFAULT_CONFIG = Path.home() / ".config" / "xaana-caption-relay" / "device.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def api(base, path, token=None, body=None):
    parts = urlsplit(base)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ValueError("Server must be an HTTPS origin")
    headers = {"Content-Type": "application/json", "User-Agent": "Xaana-Caption-Relay/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(base.rstrip("/") + "/api/caption-relay/" + path,
                  data=json.dumps(body or {}).encode(), headers=headers, method="POST")
    # Never forward credentials on redirects, including HTTPS -> HTTP.
    with build_opener(NoRedirect).open(req, timeout=25) as response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Response too large")
        return json.loads(data) if data else {}


def save_config(path, config):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Never truncate an existing device credential during a second pairing.
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(config, stream)
    if os.name == "nt":
        identity = subprocess.check_output(["whoami"], text=True).strip()
        result = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", identity + ":(F)"],
                                capture_output=True)
        if result.returncode:
            path.unlink()
            raise RuntimeError("Unable to protect device token file")


def fetch(video_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Invalid job video ID")
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("fetch.py")), video_id],
                                capture_output=True, text=True, encoding="utf-8", check=True, timeout=90,
                                env={k: v for k, v in os.environ.items()
                                     if k in ("PATH", "SYSTEMROOT", "WINDIR", "LANG")})
        if len(result.stdout) > 2_000_000:
            return {"error": "fetch_failed"}
        result = json.loads(result.stdout)
        return result if "transcript" in result or "error" in result else {"error": "fetch_failed"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except (ValueError, subprocess.CalledProcessError):
        return {"error": "fetch_failed"}


def run(config, once=False):
    failures = 0
    while True:
        delay = 20
        try:
            response = api(config["server"], "claim", config["token"])
            job = response.get("job")
            if job:
                video_id = job["video_id"]
                LOG.info("%s: claimed; fetching captions", video_id)
                result = fetch(video_id)
                api(config["server"], "complete", config["token"],
                    {"video_id": video_id, "lease_token": job["lease_token"], **result})
                LOG.info("%s: %s", video_id, "captions uploaded" if "transcript" in result else result["error"])
                delay = 30
            else:
                LOG.info("Waiting for caption jobs")
            failures = 0
        except HTTPError as exc:
            if exc.code in (401, 403):
                LOG.error("Device authorization rejected. Revoke/pair this device in Xaana Admin.")
                return 2
            LOG.warning("Server returned HTTP %d; retrying later", exc.code)
            failures += 1
        except (OSError, ValueError, KeyError):
            LOG.warning("Connection or response unavailable; retrying later")
            failures += 1
        if once:
            return 1 if failures else 0
        delay = max(delay, min(300, 20 * 2 ** min(failures, 4)))
        time.sleep(delay + random.uniform(0, 3))


def main():
    parser = argparse.ArgumentParser(description="Xaana Caption Relay")
    parser.add_argument("command", choices=("pair", "run"), nargs="?", default="run")
    parser.add_argument("--server", default="https://xaana.club")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "pair":
        if args.config.exists():
            parser.error("This device already has a token. Revoke it before pairing again.")
        code = getpass.getpass("One-time pairing code from Xaana Admin > Caption Relay: ").strip()
        try:
            paired = api(args.server, "pair", body={"code": code})
            save_config(args.config, {"server": args.server, **paired})
        except (HTTPError, OSError, ValueError, RuntimeError):
            LOG.error("Pairing failed. Check the code, connection and config directory permissions.")
            return 1
        LOG.info("Paired as %s. Ready to run.", paired["name"])
        return 0
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        parser.error("Pair this device first: xaana-caption-relay pair")
    try:
        return run(config, args.once)
    except KeyboardInterrupt:
        LOG.info("Stopped")
        return 0
