# VK → Telegram через Callback API

Отдельный сервис для одной связки «сообщество VK → Telegram-канал». VK сообщает серверу о новой записи через Callback API, сервер надёжно сохраняет событие в SQLite и публикует его через обычного Telegram-бота. Личный Telegram-аккаунт, `api_id`, `api_hash` и номер телефона не нужны.

## Поддерживаемые публикации

- только текст;
- одна фотография;
- текст с фотографией — одним Telegram-постом;
- несколько фотографий — одним альбомом до 10 элементов;
- прямое видео VK в MP4;
- смешанный альбом из фото и прямых видео, если Telegram принимает сочетание.

К каждому посту добавляется ссылка на оригинал VK. Если подпись вместе со ссылкой длиннее 1024 символов, первые 1024 символа идут в подпись, остаток — отдельным сообщением из-за ограничения Telegram.

Стандартный Telegram Bot API принимает загружаемое видео до 50 МБ. Проект использует безопасный предел 49 МБ. Если VK не отдаёт прямой MP4 или видео закрыто/внешнее, сервис публикует ссылку на видео. Если прямой файл уже найден, но при скачивании оказался крупнее 49 МБ, задание получает `failed` до публикации; ссылка на исходный пост остаётся доступна оператору по ключу задания. Фотографии ограничены 9 МБ при загрузке. Пост с более чем 10 доступными медиафайлами также получает `failed` до отправки: это предотвращает частичную публикацию и дубли при повторе.

Редактирование и удаление записи VK после публикации не синхронизируется. Репосты обрабатываются как текст/вложения внешнего поста только в той мере, в которой VK помещает их в основное событие; вложенная `copy_history` отдельно не разворачивается.

## Как работает надёжность

Callback обработчик проверяет числовой ID сообщества и секрет сравнением без утечки по времени. Повтор одного события получает тот же ключ `vk:<owner_id>:<post_id>` и не создаёт дубликат в очереди. Ответ `ok` возвращается только после записи в SQLite.

Перед отправкой задание получает статус `sending`. Если процесс остановился в этот момент либо связь оборвалась во время запроса Telegram, после запуска будет статус `uncertain`: сервис не отправит пост повторно вслепую. Оператор проверяет Telegram и выбирает `resolve` или `retry`. Гарантировать exactly-once невозможно, потому что у методов отправки Telegram Bot API нет пользовательского idempotency key.

## Что потребуется

- VPS с Ubuntu/Debian, Python 3.10+, публичным IP и открытыми 80/443;
- доменное имя, направленное A-записью на VPS;
- HTTPS-сертификат, например Let's Encrypt;
- пользовательский VK access token администратора с доступом к видео;
- Telegram-бот от [@BotFather](https://t.me/BotFather), добавленный администратором канала с правом публикации;
- числовой ID канала вида `-100…`.

Если VPS не может напрямую подключиться к Telegram, понадобится локальный HTTP- или SOCKS-прокси. Проект поддерживает адреса вида `socks5h://127.0.0.1:12334`; суффикс `h` передаёт прокси также разрешение DNS-имён. Через прокси идут только обращения к Telegram, а фотографии и видео скачиваются с VK напрямую.

## Переменные `.env`

Скопируйте `.env.example` в `.env`. Файл содержит секреты, его права должны быть `600`, его нельзя отправлять в Git.

- `VK_GROUP_ID` — положительный ID сообщества, например `157689028`.
- `VK_CALLBACK_SECRET` — случайная строка, которую вы зададите и в VK, и в `.env`.
- `VK_CONFIRMATION` — строка подтверждения сервера, которую показывает VK при добавлении Callback-сервера.
- `VK_USER_TOKEN` — пользовательский access token администратора с доступом к видео. Он нужен для получения прямого MP4 через `video.get`: официальная схема VK API 5.199 разрешает этот метод только токену типа `user`. Ключ сообщества для этого метода не подходит.
- `TELEGRAM_BOT_TOKEN` — токен от BotFather.
- `TELEGRAM_CHAT_ID` — ID Telegram-канала.
- `TELEGRAM_PROXY_URL` — необязательный адрес локального HTTP/SOCKS-прокси. Оставьте пустым при прямом доступе. Для Hiddify на порту 12334 используйте `socks5h://127.0.0.1:12334`.
- `CALLBACK_PATH` — путь HTTPS URL. Если меняете его, измените `location` в nginx.
- `MEDIA_LIMIT_MB` — максимум видео; значение выше 49 автоматически ограничивается 49.

## Локальная проверка на сервере

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
nano .env
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m vk_to_tg check
```

`check` проверяет токен бота, его право публикации, пользовательский токен VK и доступность сообщества. Ничего не публикует.

## Локальный прокси Hiddify

Для сервера, где Telegram недоступен напрямую, можно запустить Hiddify Core как отдельную службу. В репозитории есть `deploy/hiddify-paper.service`: она читает подписку из `/etc/hiddify-paper/subscription.txt` и открывает смешанный HTTP/SOCKS-порт только для локального использования на `12334`. Храните файл подписки вне Git и выдайте его группе `paper-vpn` с правами `640`.

После установки `hiddify-core` создайте системного пользователя и каталоги, затем установите службу:

```bash
sudo useradd --system --home /var/lib/hiddify-paper --shell /usr/sbin/nologin paper-vpn
sudo install -d -o paper-vpn -g paper-vpn -m 700 /var/lib/hiddify-paper
sudo chown root:paper-vpn /etc/hiddify-paper/subscription.txt
sudo chmod 640 /etc/hiddify-paper/subscription.txt
sudo cp deploy/hiddify-paper.service /etc/systemd/system/hiddify-paper.service
sudo systemctl daemon-reload
sudo systemctl enable --now hiddify-paper.service
```

Проверьте, что порт слушает только loopback-адрес, и что Telegram отвечает через него:

```bash
sudo ss -ltnp | grep 12334
curl --proxy socks5h://127.0.0.1:12334 -I https://api.telegram.org/
```

Укажите в `.env` `TELEGRAM_PROXY_URL=socks5h://127.0.0.1:12334`. Чтобы основной сервис запускался после прокси, установите systemd drop-in:

```bash
sudo mkdir -p /etc/systemd/system/vk-to-tg.service.d
sudo cp deploy/vk-to-tg-proxy.conf /etc/systemd/system/vk-to-tg.service.d/proxy.conf
sudo systemctl daemon-reload
```

## Установка

Распакуйте проект в `/opt/projects/vk-to-tg-callback`, создайте отдельного системного пользователя и окружение:

```bash
sudo useradd --system --home /opt/projects/vk-to-tg-callback --shell /usr/sbin/nologin vk-to-tg
sudo mkdir -p /opt/projects/vk-to-tg-callback/data
sudo python3 -m venv /opt/projects/vk-to-tg-callback/.venv
sudo /opt/projects/vk-to-tg-callback/.venv/bin/pip install -r /opt/projects/vk-to-tg-callback/requirements.txt
sudo chown -R root:vk-to-tg /opt/projects/vk-to-tg-callback
sudo chown vk-to-tg:vk-to-tg /opt/projects/vk-to-tg-callback/data
sudo chmod 700 /opt/projects/vk-to-tg-callback/data
sudo chmod 640 /opt/projects/vk-to-tg-callback/.env
sudo cp deploy/vk-to-tg-web.service /etc/systemd/system/vk-to-tg.service
sudo systemctl daemon-reload
sudo systemctl enable --now vk-to-tg
```

Установите nginx и Certbot. В `deploy/nginx.conf` замените `YOUR_DOMAIN`, скопируйте конфигурацию в `/etc/nginx/sites-available/vk-to-tg`, создайте ссылку в `sites-enabled`, проверьте и перечитайте nginx. Затем Certbot добавит HTTPS и перенаправление:

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/vk-to-tg
sudo ln -s /etc/nginx/sites-available/vk-to-tg /etc/nginx/sites-enabled/vk-to-tg
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d bot.example.ru
sudo nginx -t
sudo systemctl reload nginx
```

Внешний адрес Callback будет `https://bot.example.ru/vk/callback`. Приложение слушает только `127.0.0.1:8080`, поэтому напрямую из интернета оно недоступно.

## Настройка VK Callback API

1. Сообщество → Управление → Работа с API → Callback API.
2. Добавьте сервер с адресом `https://ваш-домен/vk/callback`.
3. Впишите тот же секрет, что в `VK_CALLBACK_SECRET`.
4. VK покажет строку подтверждения. Запишите её в `VK_CONFIRMATION`, перезапустите службу и нажмите подтверждение сервера в VK.
5. В типах событий включите «Добавление записи на стену» (`wall_post_new`).

Не открывайте путь Callback без секрета и не публикуйте `.env`.

## Проверка работы

```bash
sudo systemctl status vk-to-tg
sudo journalctl -u vk-to-tg -f
curl -fsS https://ваш-домен/health
```

Опубликуйте последовательно тестовый текст, фото с подписью, альбом и короткое MP4-видео в VK. Проверьте, что каждый вариант появился в Telegram один раз.

## Очередь и восстановление

Остановите службу перед административной командой:

```bash
sudo systemctl stop vk-to-tg
cd /opt/projects/vk-to-tg-callback
sudo -u vk-to-tg .venv/bin/python -m vk_to_tg status
```

Статусы: `pending`, `sending`, `done`, `failed`, `uncertain`. Для явной исправленной ошибки:

```bash
sudo -u vk-to-tg .venv/bin/python -m vk_to_tg retry 'vk:-157689028:123'
```

Для `uncertain` сначала проверьте канал. Если пост уже есть:

```bash
sudo -u vk-to-tg .venv/bin/python -m vk_to_tg resolve 'vk:-157689028:123'
```

Если его нет — используйте `retry`. Затем `sudo systemctl start vk-to-tg`.

Делайте резервную копию всей папки `data` только при остановленной службе. Потеря SQLite сбрасывает защиту от повторов.

## Несколько связок

Один экземпляр обслуживает одну пару. Для следующего сообщества создайте отдельную копию каталога, `.env`, базу, внутренний порт, Callback path, systemd unit и nginx `location`. Это намеренное разделение: сбой или токен одной связки не влияет на остальные.

## Источники ограничений

- [Telegram Bot API: sendVideo и лимиты загрузки](https://core.telegram.org/bots/api#sendvideo)
- [Telegram Bot API: sendMediaGroup](https://core.telegram.org/bots/api#sendmediagroup)
- [Официальная схема VK API 5.199](https://github.com/VKCOM/vk-api-schema)
- [Схема метода `video.get`: только пользовательский токен](https://github.com/VKCOM/vk-api-schema/blob/master/video/methods.json)
