# Telegram support

The public support bot is separate from the private admin-notification bot.
Users write to it in a private chat; each open request becomes a topic in one
private forum supergroup. Messages are copied both ways by the bot.

## Configuration

Set four values in the deployment `.env` (never commit the real values):

```dotenv
SUPPORT_TELEGRAM_BOT_TOKEN=<token from BotFather>
SUPPORT_TELEGRAM_BOT_USERNAME=<username without @>
SUPPORT_TELEGRAM_WEBHOOK_SECRET=<random URL-safe secret>
SUPPORT_TELEGRAM_SETUP_SECRET=<temporary random URL-safe secret>
```

Generate both secrets independently, for example with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Deploy the API so migration `0023` and the new variables are active, then run
inside the API container:

```bash
python scripts/configure_support_telegram.py
```

In the private support supergroup:

1. Enable Topics.
2. Add the support bot as an administrator with permission to manage topics.
3. Send `/setup <SUPPORT_TELEGRAM_SETUP_SECRET>`.
4. After the bot confirms the group, delete that message and replace or clear
   `SUPPORT_TELEGRAM_SETUP_SECRET` in the deployment environment.

The bot stores the group's numeric chat id itself. No third-party ID bot is
needed. If the support group is ever replaced, set a new temporary setup
secret and repeat `/setup` in the new group.

## Conversation lifecycle

- An authenticated site user receives a one-time `t.me` deep link. It links
  the support chat to the site account and source page.
- A guest is identified only by Telegram id/name/username.
- The first message creates a ticket and a forum topic. Text, photos,
  documents, video, audio, voice messages and stickers are copied without
  downloading them to application storage.
- An administrator writes normally inside the topic; the bot copies the
  response to the user's private chat.
- `Закрити звернення` closes the ticket and topic. The user's next message
  opens a new ticket.

The webhook checks Telegram's `X-Telegram-Bot-Api-Secret-Token`. Updates from
other groups are ignored; only the group registered with `/setup` can send
answers or close tickets.
