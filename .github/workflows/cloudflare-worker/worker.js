/**
 * Cloudflare Worker — instant Telegram webhook receiver for the "дз" trigger.
 *
 * Telegram calls this Worker the instant a message is sent to the bot
 * (setWebhook — no polling, no delay). If the message text is "дз" (any
 * case, any surrounding punctuation — "Дз?", "ДЗ!!!", "дз." all match),
 * the Worker asks GitHub to run the dz_on_demand.yml workflow via a
 * repository_dispatch event, passing along the chat id to reply to.
 * The actual login + diary scraping + Telegram reply happens in that
 * GitHub Actions workflow (this Worker never touches your diary
 * credentials — it only forwards a trigger).
 *
 * Required Worker environment variables/secrets (set in the Cloudflare
 * dashboard under Settings → Variables and Secrets — see README):
 *   GITHUB_REPO     - "your-username/your-repo-name"
 *   GITHUB_TOKEN    - a GitHub personal access token that can dispatch
 *                      repository_dispatch events on that repo
 *   WEBHOOK_SECRET  - a random string you also pass to Telegram's
 *                      setWebhook (secret_token) — rejects anything that
 *                      isn't really from Telegram
 */

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("OK", { status: 200 });
    }

    if (env.WEBHOOK_SECRET) {
      const secretHeader = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
      if (secretHeader !== env.WEBHOOK_SECRET) {
        return new Response("Forbidden", { status: 403 });
      }
    }

    let update;
    try {
      update = await request.json();
    } catch (err) {
      return new Response("OK", { status: 200 }); // ignore malformed bodies
    }

    const message = update.message;
    const text = message && typeof message.text === "string" ? message.text : "";
    const chatId = message && message.chat ? message.chat.id : null;

    // Keep only letters (incl. Cyrillic), lowercase — so "Дз", "дз?",
    // "ДЗ!!!", "дз пожалуйста" (becomes "дзпожалуйста", won't match — see
    // note below) all normalize predictably.
    const normalized = text.replace(/[^a-zA-Zа-яА-ЯёЁ]/g, "").toLowerCase();

    if (chatId && normalized === "дз") {
      await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "dz-bot-cloudflare-worker",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          event_type: "dz_request",
          client_payload: { chat_id: String(chatId) },
        }),
      });
    }

    // Telegram just needs a fast 200 — the real reply comes later from the
    // GitHub Actions workflow, straight to Telegram's API.
    return new Response("OK", { status: 200 });
  },
};
