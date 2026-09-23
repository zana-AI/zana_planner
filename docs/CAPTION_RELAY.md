# Xaana Caption Relay

Caption requests are durable and keyed by YouTube video ID:
cache → one background server attempt (45-second deadline) → residential relay
on failure → cache. A cached video never needs another download. Viewer requests
only query the cache/queue and poll while pending. The bot queues on receipt,
save and assignment; these requests are idempotent.

The server dispatcher runs in the webapp, claims with PostgreSQL row locks,
and performs no network work inside a database transaction. An expired cloud
lease falls through to the residential stage. Each relay handles one job at a
time, with a 180-second lease, a 90-second fetch deadline, 30-second pacing and
at most three attempts. Failure retries back off; exhausted jobs remain failed
instead of restarting every time a user opens a video. A device being offline
leaves its unclaimed work queued.

## Install on Raspberry Pi / Linux

Use a current 64-bit Raspberry Pi OS with Python 3.10+. The worker needs
outbound HTTPS, no inbound ports. Downloading the bundle needs no account or
repository credentials:

~~~sh
sudo apt-get install python3-venv curl unzip
sudo useradd --system --home /var/lib/xaana-caption-relay --shell /usr/sbin/nologin xaana-caption
sudo install -d -m 700 -o xaana-caption -g xaana-caption /var/lib/xaana-caption-relay
sudo install -d -m 755 /opt/xaana-caption-relay
curl --fail --proto '=https' --tlsv1.2 https://xaana.club/api/caption-relay/download -o caption-relay.zip
unzip caption-relay.zip
sudo python3 -m venv /opt/xaana-caption-relay/venv
sudo /opt/xaana-caption-relay/venv/bin/pip install ./xaana-caption-relay
~~~

In Xaana, open **Admin → Caption Relay**, enter a device name, and create a
pairing code. Run this command on the Pi and paste the code at the hidden prompt:

~~~sh
sudo -u xaana-caption /opt/xaana-caption-relay/venv/bin/xaana-caption-relay pair --config /var/lib/xaana-caption-relay/device.json
sudo install -m 644 xaana-caption-relay/xaana-caption-relay.service /etc/systemd/system/xaana-caption-relay.service
sudo systemctl daemon-reload
sudo systemctl enable --now xaana-caption-relay
journalctl -u xaana-caption-relay -f
~~~

One-time pairing expires after ten minutes. The service stores a generated
device token in a mode-0600 file, then runs unattended under its dedicated
unprivileged OS account. systemd hides home directories, makes the filesystem
read-only except the state directory, removes Linux capabilities, and limits
memory and processes. Revoke a device in the same admin screen to invalidate
its token and active lease immediately.

For updates, download the bundle again and run pip install --upgrade against
the extracted directory, then restart the service. Fetching libraries update
frequently; they are minimum-version constrained, not frozen indefinitely.

## Windows / foreground development

~~~powershell
python -m pip install ./scripts/caption_relay
xaana-caption-relay pair
xaana-caption-relay run
~~~

The compatibility entry point is `python scripts/transcript_fetch_service.py`.
It now uses HTTPS only. The token is under
`~/.config/xaana-caption-relay/device.json`; Windows ACLs restrict it to the
current account. This is not an OS sandbox: running as an existing administrator
does not remove that account's pre-existing SSH keys or other privileges.
For isolation use the dedicated Linux service user on the Pi. Do not copy
your .ssh directory, .env files, application database credentials, or the whole
development account to a worker device.

## Security model and limits

- HTTPS with certificate verification; no token in URLs, arguments or logs;
  redirects are rejected. Pairing codes and tokens have 256 bits of randomness.
- Tokens are stored hashed in the database. Pairing is atomic and single-use.
  Tokens are revocable, device-specific and do not authenticate as Xaana users.
- Only admins can create/revoke devices. Workers cannot enqueue arbitrary
  videos, enumerate libraries, issue SQL, SSH to the VM, or access other APIs.
- Each result must match the device, video and an unexpired random lease.
  Revocation and completion serialize on the device record. Stale submissions
  cannot overwrite data. Cache writes and job completion commit atomically.
- Uploads have a 2 MB body limit, 5,000-cue limit, 1 MB text limit, finite
  timestamps and validated fields. Claims have a database-backed cooldown;
  the API also applies a bounded per-process request throttle.
- Devices are trusted caption producers. A compromised approved device can
  falsify captions for its assigned jobs until revoked. Automatic validation
  checks structure, not whether each word is faithful to the video.
- Unavailable/disabled captions are not made available by this service, and a
  residential address does not guarantee YouTube accepts every request.
- Existing administrative SSH access on a development laptop is independent
  of the relay. Migrating the worker does not revoke those administrator keys.

No production DB credentials or SSH keys are needed by a relay. Anonymous
workers are deliberately unsupported because they could claim jobs and poison
the caption cache. Pairing is the single authorization step.

Implementation guidance:
[OWASP REST security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
and [systemd service sandboxing](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html).
