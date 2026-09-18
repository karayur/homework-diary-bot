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

## 6. Add the kids' Telegram accounts too

Everyone listed gets the exact same message (both sons' homework combined) —
this is the simplest setup, no per-son routing.

1. Send each son the bot's link: `https://t.me/<bot_username>` (or they can
   just search for the bot's username in Telegram).
2. Each of them opens the chat and sends any message to the bot (e.g.
   `/start`) — same one-time requirement as with your own chat in step 1.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` again — you'll now
   see a message entry per person, each with its own `"chat":{"id": ...}`.
   Match them up by `"from":{"first_name": ...}` to know whose id is whose.
4. Edit the existing `TELEGRAM_CHAT_ID` secret (**Settings → Secrets and
   variables → Actions → TELEGRAM_CHAT_ID → Update**) and put all the ids
   separated by commas, no spaces needed either way, e.g.:
   `111111111,222222222,333333333`
5. Re-run the workflow manually once (Actions → Run workflow) to confirm
   everyone gets the message.

No other secret or file needs to change — `homework_check.py` already
splits `TELEGRAM_CHAT_ID` on commas and sends to each one.

## 7. On-demand: reply when someone writes "дз"

Anyone in the chat (you or the kids) can send the bot "дз" — any case,
any punctuation ("Дз", "ДЗ!!!", "дз?" all count) — and get homework for
the nearest school day back, addressed only to them (not broadcast to
everyone). This needs one more free service — **Cloudflare Workers** — to
catch the message the instant it arrives (GitHub alone can't react to a
Telegram message in real time, only on its own schedule).

How it fits together: Telegram → Cloudflare Worker (instant) → tells
GitHub to run `dz_on_demand.yml` → that workflow logs in, reads the
diary, and replies. The Worker never sees your diary password — it only
forwards a trigger. Total time from message to reply is usually **1-3
minutes** (most of it is GitHub Actions installing Playwright/Chromium
and the actual login+scrape — the Worker itself reacts in well under a
second).

### 7.1 Create a GitHub token the Worker can use to trigger the workflow

1. Go to **github.com/settings/tokens** → **Fine-grained tokens** → **Generate
   new token**.
2. Give it a name, set **Repository access** to "Only select repositories"
   and pick this repo.
3. Under **Permissions → Repository permissions**, set **Contents** to
   **Read and write** (this is what allows sending a `repository_dispatch`
   event).
4. Generate it and save the token somewhere safe — you'll paste it into
   Cloudflare next, and GitHub won't show it again.

### 7.2 Create the Cloudflare Worker

1. Sign up (free) at **dash.cloudflare.com** if you don't have an account.
2. **Workers & Pages → Create → Create Worker**. Give it any name (e.g.
   `dz-bot-webhook`) and deploy the default "Hello World" — you'll replace
   the code next.
3. Open the Worker → **Edit code**, delete everything, and paste in the
   contents of `cloudflare-worker/worker.js` from this project. **Deploy**.
4. Back in the Worker's **Settings → Variables and Secrets**, add these
   variables — `GITHUB_REPO` can stay plain text, the other three should
   be **secret** (use "Encrypt"):
   | Name | Value | Secret? |
   |---|---|---|
   | `GITHUB_REPO` | `your-username/your-repo-name` | no |
   | `GITHUB_TOKEN` | the fine-grained token from step 7.1 | yes |
   | `WEBHOOK_SECRET` | any random string you make up (e.g. 20+ random characters) | yes |
   | `TELEGRAM_BOT_TOKEN` | the same bot token you already put in the GitHub secrets (step 3) | yes |
5. Note the Worker's URL, shown at the top of its page — something like
   `https://dz-bot-webhook.<your-subdomain>.workers.dev`.

### 7.3 Point Telegram at the Worker

Open this URL in a browser once (fill in your bot token, the Worker URL,
and the same `WEBHOOK_SECRET` you set in step 7.2):

```
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<WORKER_URL>&secret_token=<WEBHOOK_SECRET>
```

You should get back `{"ok":true,"result":true,...}`. From now on Telegram
pushes every message to the Worker instead of you having to poll for
them.

### 7.4 Test it

Send "дз" to the bot from your phone. You should get "Подожди
минуту-полторы, читаю дневник…" back almost instantly (that's the Worker
itself replying), then the actual homework a minute or two later (that's
the GitHub Actions job finishing). If the first message never arrives:
check the Worker's **Logs** tab in Cloudflare (to confirm it received the
message from Telegram). If the first message arrives but the homework
never does: check the **Actions** tab in GitHub for a "DZ on-demand
reply" run (to see if it fired and whether it failed at login/scraping,
same debugging as the daily job).

### Notes on this part

- This only reacts to a message whose text, after stripping punctuation
  and lowercasing, is exactly "дз" — "дз" on its own line, "Дз?", "ДЗ!!"
  all match; "дз пожалуйста" (extra words) does not, by design, to avoid
  false triggers.
- The daily scheduled broadcast (`homework_diary.yml`) is unaffected —
  this is a separate workflow (`dz_on_demand.yml`) that only replies to
  whoever asked.
- If you'd rather skip Cloudflare entirely and accept up to a ~5 minute
  delay, the alternative is a GitHub Actions workflow polling Telegram's
  `getUpdates` every 5 minutes (GitHub's minimum schedule interval) — let
  me know and I can build that instead.

## Notes

- The scraping selectors (`.diary_row`, `.diary_cell`, the
  `data-bs-toggle="popover"` homework popovers) match the site structure
  already confirmed to work via the browser-based version of this task.
  The login form structure was separately confirmed by inspecting the
  live `/login` page (without entering any credentials).
- If the school changes the diary site's layout, this script needs the
  same kind of adjustment the original browser-based task would.
