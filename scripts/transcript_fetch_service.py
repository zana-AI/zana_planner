"""Compatibility entry point. SSH-based caption access has been retired."""
from caption_relay.client import main

if __name__ == "__main__":
    raise SystemExit(main())
