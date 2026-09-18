#!/usr/bin/env python3
"""
Homework diary check — Лицей им. С.Н. Нюберг (nyberg-am.mojo.education)

Runs headless (no local computer needed — designed for GitHub Actions),
logs into the Mojo Education parent portal, reads the homework for the
nearest school day for both sons, and sends a summary to Telegram.

Required environment variables (set as GitHub Actions secrets):
    DIARY_LOGIN        - your login (email/phone/username) for the diary site
    DIARY_PASSWORD     - your password for the diary site
    TELEGRAM_BOT_TOKEN  - token of the Telegram bot to send from (create via @BotFather)
    TELEGRAM_CHAT_ID    - your numeric Telegram chat id (see README for how to find it)

Optional:
    DIARY_BASE_URL      - defaults to https://nyberg-am.mojo.education
"""

import os
import re
import sys
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = os.environ.get("DIARY_BASE_URL", "https://nyberg-am.mojo.education").rstrip("/")

# parent-portal ids for each son (from the school-diary-mojo skill)
SONS = [
    {"name": "Юрий (9 класс)", "id": 227},
    {"name": "Илья (7 класс)", "id": 238},
]

TZ = ZoneInfo("Asia/Yerevan")


def nearest_school_day(today: date) -> date:
    """Tomorrow, or the next Monday if tomorrow falls on a weekend."""
    d = today + timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d


def clean_text(raw: str) -> str:
    raw = re.sub(r"<[^>]*>", " ", raw or "")
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


def do_login(page, username: str, password: str) -> None:
    """Login for nyberg-am.mojo.education. Selectors confirmed by inspecting
    the live login page on 2026-09-19: a single-step form at /login with
    an E-mail input (type="email"), a Пароль input (type="password"), and
    a "Войти" submit button (type="submit") — no CSRF field, no two-step
    flow. The two-step fallback below is kept just in case the school
    later changes this."""
    page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)

    pwd = page.query_selector('input[type="password"]')

    if not pwd:
        # Possibly a two-step login (identifier first, password on next screen)
        identifier = page.query_selector(
            'input[type="email"], input[name*="login" i], input[name*="email" i], input[name*="user" i]'
        )
        if identifier:
            identifier.fill(username)
            submit = page.query_selector('button[type="submit"], input[type="submit"]')
            if submit:
                submit.click()
            else:
                identifier.press("Enter")
            page.wait_for_load_state("networkidle", timeout=30000)
            pwd = page.query_selector('input[type="password"]')

    if not pwd:
        page.screenshot(path="debug_no_password_field.png", full_page=True)
        raise RuntimeError(
            "Не нашёл поле пароля на странице логина. Смотри debug_no_password_field.png "
            "в артефактах запуска и поправь селекторы в do_login()."
        )

    id_field = page.query_selector(
        'form input[type="email"], form input[name*="login" i], form input[name*="user" i], form input[type="text"]'
    )
    if id_field:
        id_field.fill(username)

    pwd.fill(password)

    submit = page.query_selector('button[type="submit"], input[type="submit"]')
    if submit:
        submit.click()
    else:
        pwd.press("Enter")

    page.wait_for_load_state("networkidle", timeout=30000)

    if page.query_selector('input[type="password"]'):
        page.screenshot(path="debug_login_failed.png", full_page=True)
        raise RuntimeError(
            "После отправки формы логина всё ещё видно поле пароля — вход не удался. "
            "Проверь DIARY_LOGIN/DIARY_PASSWORD и debug_login_failed.png."
        )


def read_day(page, son_id: int, target_date: date) -> list[dict]:
    url = f"{BASE_URL}/parent/{son_id}/diary/date/{target_date.isoformat()}"
    page.goto(url, wait_until="networkidle", timeout=30000)

    try:
        page.wait_for_selector(".diary_row", timeout=8000)
    except PlaywrightTimeoutError:
        return []

    return page.evaluate(
        """
        () => {
          function clean(html){
            return (html || '').replace(/<[^>]*>/g, ' ').replace(/\\s+/g,' ').trim();
          }
          const rows = document.querySelectorAll('.diary_row');
          const result = [];
          rows.forEach(row => {
            const cells = row.querySelectorAll(':scope > .diary_cell');
            if (cells.length < 3) return;
            const subject = clean(cells[2] ? cells[2].innerText : '');
            if (!subject) return;
            let homework = null;
            const popovers = row.querySelectorAll('[data-bs-toggle="popover"]');
            popovers.forEach(el => {
              const title = el.getAttribute('data-bs-original-title') || '';
              if (title.indexOf('Домашнее') !== -1) {
                homework = clean(el.getAttribute('data-bs-content') || '');
              }
            });
            result.push({subject, homework});
          });
          return result;
        }
        """
    )


def format_summary(target_date: date, per_son: dict) -> str:
    weekday_ru = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][
        target_date.weekday()
    ]
    lines = [f"📔 Домашнее задание на {target_date.strftime('%d.%m.%Y')} ({weekday_ru})"]

    for son_name, lessons in per_son.items():
        lines.append(f"\n👤 {son_name}")
        if not lessons:
            lines.append("Нет данных об уроках на этот день (возможно, нет расписания/каникулы).")
            continue

        no_homework_yet = []
        for lesson in lessons:
            subject = lesson["subject"]
            hw = lesson.get("homework")
            if hw:
                lines.append(f"• {subject}: {hw}")
            else:
                no_homework_yet.append(subject)

        if no_homework_yet:
            lines.append("Без домашнего задания пока: " + ", ".join(no_homework_yet))

    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram messages are capped at 4096 chars — split on line boundaries if needed.
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > 3800:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)

    for chunk in chunks:
        resp = requests.post(api_url, data={"chat_id": chat_id, "text": chunk}, timeout=15)
        resp.raise_for_status()


MAX_DAYS_AHEAD = 14  # covers most school breaks; stop searching after two weeks


def main() -> int:
    today = date.today()  # GitHub Actions runner is UTC; cron is scheduled so this is
                            # still "today" in Yerevan at the moment the job fires.
    target_date = nearest_school_day(today)

    per_son = {}
    skipped_dates = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            do_login(page, os.environ["DIARY_LOGIN"], os.environ["DIARY_PASSWORD"])

            attempts = 0
            while True:
                per_son = {son["name"]: read_day(page, son["id"], target_date) for son in SONS}
                has_lessons = any(per_son.values())  # non-empty list for at least one son
                if has_lessons or attempts >= MAX_DAYS_AHEAD:
                    break
                # No lessons at all for either son on this weekday (holiday/break) —
                # move to the next school day and try again.
                skipped_dates.append(target_date)
                target_date = nearest_school_day(target_date)
                attempts += 1

            browser.close()
    except Exception as exc:  # noqa: BLE001 - report failures to Telegram too
        try:
            send_telegram(f"⚠️ Не удалось прочитать дневник: {exc}")
        except Exception:
            pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = format_summary(target_date, per_son)
    if skipped_dates:
        skipped_str = ", ".join(d.strftime("%d.%m") for d in skipped_dates)
        summary = f"(Пропущены дни без уроков: {skipped_str})\n\n{summary}"
    print(summary)
    send_telegram(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
