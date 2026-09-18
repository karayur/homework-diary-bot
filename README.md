# Homework diary → Telegram (works even with your computer off)

Runs entirely on GitHub's servers on a daily schedule (16:00 Yerevan time),
reads tomorrow's (or next Monday's) homework for both sons from
nyberg-am.mojo.education, and sends it to a Telegram bot. No dependency on
your computer being on.

## 1. Create a dedicated Telegram bot (2 minutes)

1. In Telegram, open a chat with **@BotFather**.
2. Send `/newbot`, give it any name and a unique username ending in `bot`
   (e.g. `nyberg_homework_bot`).
3. BotFather replies with a **token** like `123456789:AAH...` — save it,
   you'll need it as `TELEGRAM_BOT_TOKEN`. 
4. Open a chat with your new bot and send it any message (e.g. "привет") —
   bots can't message you first, so this step is required once.
5. Find your numeric chat id: open this URL in a browser (replace
   `<TOKEN>`):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Look for `"chat":{"id":  ...}` in the JSON — that number is your
   `TELEGRAM_CHAT_ID`. (Alternative: message **@userinfobot**, it replies
   with your id directly.) 

## 2. Create a GitHub repository

1. Create a new **private** repository on GitHub (private, since the
   workflow will hold secrets and read your kids' school data).
2. Upload this whole `homework-diary-bot` folder to it (keep the
   `.github/workflows/homework_diary.yml` path exactly as-is — GitHub
   only picks up workflows from that folder).

## 3. Add secrets

In the repo: **Settings → Secrets and variables → Actions → New repository
secret**. Add four secrets:

| Name | Value |
|---|---|
| `DIARY_LOGIN` | your login for nyberg-am.mojo.education |
| `DIARY_PASSWORD` | your password for nyberg-am.mojo.education |
| `TELEGRAM_BOT_TOKEN` | the token from BotFather |
| `TELEGRAM_CHAT_ID` | your numeric chat id |

Nobody (including me) sees these — GitHub encrypts them and only exposes
them to your own workflow run.

## 4. Test it manually before trusting the schedule

Go to the **Actions** tab → "Homework diary check" workflow → **Run
workflow** (this is the `workflow_dispatch` trigger, it lets you fire it
on demand instead of waiting for 16:00). Watch the run: if it succeeds,
you'll get a Telegram message within ~30 seconds of it finishing.

### If the login step still fails

`do_login()` now targets the real login page structure (checked directly
on nyberg-am.mojo.education/login on 2026-09-19: a single-step form — an
`E-mail` field, a `Пароль` field, a `Войти` submit button, no CSRF token,
no two-step flow — without ever touching your actual password). So this
should work as-is. If it still fails (e.g. the school changes the login
page later):

1. Open the failed run → the "Upload debug screenshots" step → download
   `debug-screenshots` artifact. It'll show exactly what the login page
   looked like when the script got stuck.
2. Send me that screenshot (or just describe what changed) and I'll adjust
   `do_login()` precisely.

## 5. How the schedule works

- `cron: "0 12 * * *"` = 12:00 UTC daily = 16:00 Yerevan time (Armenia has
  no DST, so this stays correct year-round).
- GitHub disables scheduled workflows automatically if the repository has
  **zero activity for 60 days** — if that ever happens, any commit (or
  just re-running it manually once) re-enables it. Worth knowing since a
  silent 60-day gap is the one way this could quietly stop.
- The date logic replicates what the original task did: tomorrow, or the
  next Monday if tomorrow is a weekend.

## Notes

- The scraping selectors (`.diary_row`, `.diary_cell`, the
  `data-bs-toggle="popover"` homework popovers) match the site structure
  already confirmed to work via the browser-based version of this task.
  The login form structure was separately confirmed by inspecting the
  live `/login` page (without entering any credentials).
- If the school changes the diary site's layout, this script needs the
  same kind of adjustment the original browser-based task would.
