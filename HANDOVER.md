# SelfXTrack – moving to a new computer

This copy contains **code and documents only**: no passwords, keys, databases or build files.

## 1. Do these first (secrets that stay behind on the old laptop)
| What | Where | Why |
|---|---|---|
| **Groq AI key** | console.groq.com → API Keys → delete the old key, create a new one | The old key was saved in `backend/.env` on the old laptop |
| JWT secret + admin key | new random values in your new `backend/.env` (step 3) | The old laptop used the default values |
| Firebase / Razorpay keys (if you created any) | their consoles → rotate | Same reason |

## 2. Install
- Python 3.11+ · Android Studio (set **Gradle JDK = 17 or 21**: Settings → Build Tools → Gradle) · Docker (for production)
- Optional for firmware: ESP-IDF 5.2+

## 3. Backend (local test)
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
# fill in .env:
#   SELFX_JWT_SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
#   SELFX_ADMIN_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
#   SELFX_LLM_PROVIDER=openai  SELFX_LLM_BASE_URL=https://api.groq.com/openai/v1
#   SELFX_LLM_API_KEY=<new Groq key>  SELFX_LLM_MODEL=openai/gpt-oss-120b
.venv/bin/python -m pytest -q          # all tests should pass
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
`--host 127.0.0.1` = only your computer can reach it (the Android emulator still can, via 10.0.2.2).
Use `--host 0.0.0.0` only while testing with a real phone on your own Wi-Fi.

Simulator: `python tools/simulator.py --admin-key <your admin key> provision SX-0001`, then `run SX-0001 <device_secret>`.

## 4. Android
Open `android/` in Android Studio → Sync → Run. Debug builds may use plain HTTP to your local server;
**release builds only talk HTTPS** to `DEFAULT_SERVER` in `android/app/build.gradle.kts` – set your domain there.

## 5. Production (when you deploy)
Follow `deploy/DEPLOY.md`. Security checklist:
- `SELFX_ENV=production` – the server refuses to start with default secrets, SQLite, `*` CORS or HTTP.
- Firewall: open only **443** (and 80 for the certificate). Never open 8000, 5432 or 1883.
- MQTT: `deploy/mosquitto.prod.conf` + `mosquitto.acl` (no anonymous access, one user per tracker).
- `SELFX_TRUSTED_PROXIES` = Caddy's IP so rate limits see real client IPs.
- Firmware: generate the OTA signing key once (`firmware/sdkconfig.defaults` explains how) and keep it offline.
- Daily encrypted backups (`deploy/backup.sh`).

## 6. Security fixes done on 15 Oct 2026
- Live-location page: token checked, page safe against script injection, pinned Leaflet files (SRI), strict CSP.
- Password reset only with a reset code (not a phone-verification code); minimum password 8 characters.
- Rate limits cannot be dodged with a fake `X-Forwarded-For`; claim-code guessing is rate limited.
- Admin key compared in constant time.
- Android release builds: HTTPS only.
- MQTT production config with passwords + per-tracker topic rules; dev ports bound to this computer only.
- Firmware: verifies the server certificate (ISRG Root X1) for data and firmware downloads; OTA images must be signed.
  ⚠️ Firmware changes are written to the Quectel/ESP-IDF documentation but **not yet built or tested on hardware**.

## 6b. Places & transport (15 Oct 2026)
- Child setup has any number of **Places** (home, school, tuition, activity, family, other) with time slots,
  "late / left early" alerts and **people per place** (teacher, coach, tutor …), plus **Transport** (bus, van, auto,
  cab) with driver and optional beacon. Server: `app/places.py`, `app/routers/places.py`; app: `ui/PlacesScreen.kt`.
- Emergency: "Alert people at <current place>"; each caretaker sees only SOS events sent to their place.
- Older safe zones / school contacts / buses are moved automatically at server start (`places.migrate`).

## 6c. Map screen (15 Oct 2026)
- The live map shows **today's path** (from midnight, `GET /history?today=true`; last 24 h if nothing today yet).
  Older days: Insights → History. It follows the child until the parent drags/zooms; 📍 button = back to the child.
- "⏸ Pause route alerts" → "Only the current trip" (named: "Left Swimming at 20:20, heading to Home") or a time slider.

## 6d. AI answers + family screen (15 Oct 2026)
- `ai.brief()` = one set of facts per child (at place since / on time / until / next / trip + travel mode / bus /
  battery forecast / alerts today / paused / holiday). Used by `GET /api/family/brief` (family screen, map, Insights)
  and by the assistant's `current_status` tool, so the screen and the AI always tell the same story.
- Assistant prompt: answer first, then since-when / on time / what's next / battery only if relevant / alerts.
  Distances ignore GPS jumps (`ai.path_km`). Groq "429 busy" is retried briefly (`llm._openai_chat`).
- App: each child card shows the status line + ✨ (opens "Ask about <child>", AI language picker at the top).
  Insights = Right now + Ask + 30-day history calendar; Holidays moved to Child setup. One theme for all screens
  (`ui/Theme.kt`).

## 7. What to build next
See **`docs/ROADMAP.md`**: step 1 "It's OK" on route alerts, step 2 launch readiness (hardware, SMS, security,
translations, pilot), step 3 after first users (Plans, friend pairing, smarter route learning).

## 8. Still open (see `docs/SelfXTrack_Implementation_Report.docx`, section 6)
SMS provider (DLT templates) · login tokens: shorter lifetime + revocation, WebSocket token out of the URL ·
per-admin accounts with 2FA + audit log · share-by-email should need the other person to accept ·
encrypt data at rest · Alembic migrations · native-speaker review of all translations.
