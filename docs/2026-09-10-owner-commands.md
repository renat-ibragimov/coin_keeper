# Команды владельца — админка, часть 1 (2026-09-10)

Видимость фоновых задач: таблица `job_runs`, раздел «Фонові задачі» в `/admin`,
админский телеграм-бот, отчёт из `coin-parser`. Решения и объём — `docs/13-admin.md`.

Код готов и лежит в двух репозиториях, тесты проходят. Ниже — то, что нужно сделать
руками: секреты, бот, выкладка, проверка.

**Где сейчас код (на 2026-09-10):**

- `coin_keeper` — ветка `feat/admin-job-visibility`, пять коммитов. В `main` её нет
  намеренно: пуш в `main` сразу выкатывает, а выкатывать нужно после секретов.
  Этот файл тоже живёт в ветке.
- `coin-parser` — уже в `main` и запушен. Опасности в этом нет: отчётность включается
  только при заданных `JOB_REPORT_URL` и `JOB_REPORT_TOKEN`, без них модуль не делает
  ничего, а контейнер коллектора до п. 5 не пересобран — крон работает по старому образу.

**Порядок важен.** Секреты попадают на сервер вместе с деплоем, значит их надо завести
**до** пуша, иначе первый прогон приложения увидит пустые переменные и промолчит.

---

## 0. Дамп базы перед выкладкой

В выкладке две миграции (`0008` — `job_runs`, `0009` — `telegram_recipients` и новый вид
токена). Миграции применяются при старте контейнера, то есть пуш меняет боевую базу.

```bash
ssh coinkeeper
cd ~/coinkeeper
docker compose exec -T postgres pg_dump -U coinkeeper coinkeeper > ~/before-admin-part1.dump
ls -la ~/before-admin-part1.dump
```

---

## 1. Бот в BotFather

В телеграме, диалог с **@BotFather**:

1. `/newbot` → имя (например `Bakost Numismatics Admin`) → username, обязательно
   заканчивается на `bot` (например `bakost_admin_bot`). В ответ придёт **токен** —
   он понадобится ниже.
2. `/setjoingroups` → выбрать бота → **Disable**. Бот не должен добавляться в группы.
3. `/setprivacy` → выбрать бота → **Enable**. Бот не читает чужие сообщения в группах.
4. `/setinline` → выбрать бота → **Disable** (если предложит подтвердить — подтвердить).

Ничего больше настраивать не нужно: команды боту не регистрируем, `/last` работает и
без списка в меню.

---

## 2. Три новые переменные

Сгенерировать два секрета (третий — токен от BotFather):

```bash
python3 -c "import secrets; print('JOB_REPORT_TOKEN=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('TELEGRAM_WEBHOOK_SECRET=' + secrets.token_urlsafe(32))"
```

Добавить в `~/coinkeeper/.env` на сервере **четыре** строки (username — без `@`):

```
JOB_REPORT_TOKEN=<из первой команды>
TELEGRAM_BOT_TOKEN=<токен от BotFather>
TELEGRAM_BOT_USERNAME=<username бота, без @>
TELEGRAM_WEBHOOK_SECRET=<из второй команды>
```

```bash
ssh coinkeeper
nano ~/coinkeeper/.env      # дописать четыре строки в конец
```

**И сразу же — в секрет GitHub, иначе следующий деплой сотрёт правку** (это уже случалось,
`docs/HANDOFF.md`). На своей машине:

```bash
ssh coinkeeper "cat ~/coinkeeper/.env" > /tmp/server.env
gh secret set SERVER_ENV < /tmp/server.env --repo renat-ibragimov/coin_keeper
rm /tmp/server.env
```

Проверить, что в файле ровно четыре новые строки и ничего не потерялось:

```bash
ssh coinkeeper "grep -c '=' ~/coinkeeper/.env"
```

---

## 3. Выкладка

Работа лежит в ветке, поэтому выкладка — это слияние. До этого момента CI не запускался
ни разу: он реагирует только на `main`.

```bash
cd ~/Desktop/Work/coin_keeper
git switch main
git pull                                   # на случай, если main ушёл вперёд
git merge --no-ff feat/admin-job-visibility
git push origin main
```

Если `main` за это время изменился и слияние даёт конфликт — остановиться и разобрать
его, а не давить `-X ours`: в ветке есть миграции, и их порядок важен.

После успешного пуша ветку можно удалить, локально и на сервере GitHub:

```bash
git branch -d feat/admin-job-visibility
git push origin --delete feat/admin-job-visibility
```

Дальше CI сам: тесты → образ → деплой → фронтенд. Дождаться зелёного и проверить:

```bash
gh run list --limit 3
curl -s https://coins.renat-ibragimov.com/api/v1/health | head -c 200
```

---

## 4. Вебхук телеграма

Только после того, как деплой прошёл — маршрут должен уже существовать:

```bash
BOT=<токен от BotFather>
SECRET=<TELEGRAM_WEBHOOK_SECRET>

curl -sS "https://api.telegram.org/bot$BOT/setWebhook" \
  -d "url=https://coins.renat-ibragimov.com/api/v1/telegram/webhook" \
  -d "secret_token=$SECRET" \
  -d "drop_pending_updates=true"
```

Ответ должен быть `{"ok":true,...}`. Проверить:

```bash
curl -sS "https://api.telegram.org/bot$BOT/getWebhookInfo"
```

В ответе важно: `url` — наш, `pending_update_count` — 0, `last_error_message` — отсутствует.

---

## 5. Пересборка контейнера парсера

Через CI он не едет — образ собирается на сервере:

```bash
ssh coinkeeper
cd ~/coin-parser
git pull
docker compose --env-file ~/coinkeeper/.env \
  -f deploy/docker-compose.collector.yml build
```

Крон трогать не нужно: команда в нём не изменилась.

Именно эта пересборка и включает отчётность в парсере — до неё он ходит по старому
образу и о прогонах молчит, даже когда переменные из п. 2 уже на месте.

---

## 6. Проверка

### 6.1. Подключить телеграм

1. Открыть `https://coins.renat-ibragimov.com/admin` под своим аккаунтом (роль admin).
2. Карточка «Сповіщення в Telegram» → **«Підключити Telegram»**. Откроется бот.
3. Нажать в боте **Start**. Бот отвечает «✅ Готово…», а карточка на сайте сама
   переключается в «Підключено» — она опрашивает статус раз в три секунды.

Если бот молчит — смотреть `getWebhookInfo` (п. 4) и логи API:

```bash
ssh coinkeeper "cd ~/coinkeeper && docker compose logs --tail 50 api | grep -i telegram"
```

### 6.2. Прогон и отчёт

Запустить ночной шаг руками, не дожидаясь 03:15. Он идемпотентен: повтор в тот же день
ничего не дублирует, вторая котировка той же даты просто заменит первую.

```bash
ssh coinkeeper
tmux new -s prices          # прогон идёт минутами, сессия рвётся
~/coin-parser/deploy/run-update-prices.sh
```

Ожидаемое:

- в конце вывода — знакомая строка `update-prices ok series=… inserted=… errors=0`
  и перед ней строчка `[job-report] run <N> opened`;
- в телеграм приходит короткое сообщение «✅ Оновлення цін — усе гаразд» с числами;
- на `/admin` в списке появился прогон со статусом «Успішно»; клик по статусу
  открывает карточку со счётчиками.

### 6.3. Команда боту

Отправить боту `/last` — он ответит тем же отчётом о последнем прогоне.

---

## 7. Если что-то пошло не так

- **Прогон отработал, но в телеграме тихо.** Проверить, что чат подключён (карточка
  в админке) и что в `.env` есть `TELEGRAM_BOT_TOKEN`. Без токена бот пишет в лог
  вместо чата — это штатное поведение локальной машины, на сервере означает забытую
  переменную.
- **`[job-report] could not reach …`** в выводе прогона. Отчёт не дошёл, но сами цены
  собраны и записаны — это разные вещи по построению. Причина обычно в
  `JOB_REPORT_TOKEN`: он должен быть одинаковым в `.env` (его читают и API, и парсер).
- **Прогон висит в «Виконується»** дольше нескольких часов — контейнер умер, не успев
  закрыть запись. Это ровно тот случай, ради которого запись открывается заранее;
  сторожа, который сообщит об этом сам, пока нет (`13-admin.md`, 2.7).
- **Откат.** Восстановление базы из дампа п. 0:

  ```bash
  ssh coinkeeper
  cd ~/coinkeeper
  docker compose exec -T postgres psql -U coinkeeper -d coinkeeper < ~/before-admin-part1.dump
  ```

---

## Чего в этой части нет

Сторожа «прогон не пришёл» (ждёт брокера), редактора каталога, экрана пользователей и
ревью новых монет — это части 2–4, `docs/13-admin.md`.
