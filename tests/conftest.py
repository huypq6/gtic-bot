"""Test config — do not connect to Binance WS in tests/CI."""

from app.config import settings

settings.feed_autostart = False
