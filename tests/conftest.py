"""Test config — không kết nối Binance WS trong test/CI."""

from app.config import settings

settings.feed_autostart = False
