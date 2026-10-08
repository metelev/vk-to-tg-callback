#!/bin/sh

check() {
  curl -fsS     --proxy http://127.0.0.1:12334     --connect-timeout 5     --max-time 15     -o /dev/null     https://api.telegram.org/
}

if check; then
  exit 0
fi

sleep 3

if check; then
  exit 0
fi

logger -t vk-tg-proxy "Telegram proxy failed; restarting Hiddify"
systemctl restart hiddify-paper.service
sleep 8

if check; then
  logger -t vk-tg-proxy "Telegram proxy recovered"
  exit 0
fi

logger -t vk-tg-proxy "Telegram proxy still unavailable"
exit 1
