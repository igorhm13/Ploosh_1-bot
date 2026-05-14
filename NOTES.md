# Ploosh Bot — Project Notes

## What is Ploosh?
A Telegram bot named **Ploosh** 🧸 — a plush baby bear avatar bot.
- Personality: warm, shy, self-aware plush teddy bear
- Language: Russian
- Main feature: weather reports with clothing advice

---

## GitHub
- Repo: https://github.com/igorhm13/Ploosh_1-bot
- Main file: `main.py` (938 lines)
- Dependencies: `requirements.txt` (python-telegram-bot==20.7, httpx)

---

## GCP Deployment
- **Project:** aqueous-vial-457909-p8
- **VM name:** utest-bot
- **Zone:** us-central1-a
- **Bot directory on VM:** /home/igor_hm_13/Ploosh_1-bot/
- **Main file on VM:** /home/igor_hm_13/Ploosh_1-bot/main.py

---

## Systemd Service
The bot runs as a systemd service named `ploosh`.

- **Service file:** /etc/systemd/system/ploosh.service
- **Auto-restarts:** yes (RestartSec=5)
- **Auto-starts on reboot:** yes (enabled)
- **TOKEN:** stored in the service file as `Environment=TOKEN=...` (NOT in the code)

Useful commands (run on the VM):
```bash
sudo systemctl status ploosh       # check if running
sudo systemctl restart ploosh      # restart after code update
sudo journalctl -u ploosh -f       # live logs
```

---

## Updating the Bot
To deploy a new version from GitHub:
```bash
cd /home/igor_hm_13/Ploosh_1-bot
git checkout main.py        # discard any local changes
git pull origin main        # pull latest from GitHub
sudo systemctl restart ploosh
```

Or from GCP Cloud Shell in one line:
```bash
gcloud compute ssh utest-bot --zone=us-central1-a --project=aqueous-vial-457909-p8 --command="cd /home/igor_hm_13/Ploosh_1-bot && git checkout main.py && git pull origin main && sudo systemctl restart ploosh && sudo systemctl status ploosh"
```

---

## Code Architecture (main.py)
- **Database:** SQLite (`users.db`) — stores user_id, name, honey_level, hurt_level, msg_count, lat, lon, place, morning_enabled
- **Weather:** Open-Meteo API (free, no key needed)
- **Geocoding:** Nominatim (reverse geocoding for city name)
- **Token:** read from `os.environ.get("TOKEN")`

### Key handlers:
| Handler | Trigger |
|---|---|
| `start` | /start command |
| `handle_message` | All text messages |
| `handle_location` | Location sharing |
| `handle_dress_callback` | "Как одеться?" inline button |
| `handle_back_weather` | "Back to weather" inline button |
| `morning_weather` | Daily job at 08:00 UTC |
| `cmd_weather` | /weather command (fetches real weather) |

### Conversation triggers (in order of priority):
1. Name detection (меня зовут / я — / зови меня)
2. Rudeness detection → hurt_level +1
3. Greetings (привет)
4. Identity (кто ты)
5. Thanks → honey_level +1
6. Praise → honey_level +1
7. Good morning / good night
8. Sad / tired
9. Walk question → redirects to weather
10. Nice weather question → redirects to weather
11. Help
12. Morning messages on/off
13. Clothing advice (холодно / жарко / куртка / как одеться) → weather-based
14. Weather (погода / градус / дождь / зонт)

---

## Fixes History
| Date | Fix |
|---|---|
| 2026-05-14 | Set up systemd service (ploosh.service) |
| 2026-05-14 | Removed is_cold/is_hot early-return blocks (were shadowing weather-based clothing advice) |
| 2026-05-14 | Removed unused `plush_reply_inline` function |
| 2026-05-14 | Fixed /weather command to actually fetch and show real weather |
