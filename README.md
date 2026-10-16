# SelfXTrack – Phases 1–6 (software complete, waiting for hardware)

Child / elderly safety tracker: **device firmware + backend server + Android parent app**.

Phase 1 delivers the end-to-end core:
**device sends location + SOS → server → parent app shows live map + SOS alert.**

```
SelfXTrack/
├── backend/        FastAPI server (API, database, SOS logic, WebSocket live updates, MQTT bridge)
├── android/        Android parent app (Kotlin + Jetpack Compose, OpenStreetMap)
├── firmware/       ESP-IDF firmware for the V1.1 board (ESP32-S3-MINI + Quectel EG800K)
├── tools/          Device simulator (test everything before hardware arrives)
├── deploy/         Mosquitto (MQTT) config
└── docker-compose.yml   PostgreSQL + MQTT + API for a server
```

---

## 1. Run the backend on your computer (5 minutes)

Needs Python 3.10+.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # edit secrets later
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API docs (try every endpoint): http://localhost:8000/docs
- Runs on SQLite by default. For production use PostgreSQL (see `docker-compose.yml`).
- Tests: `pytest -q`

### Or with Docker (server-style: PostgreSQL + MQTT + API)
```bash
docker compose up --build
```

## 2. Test without hardware (simulator)

```bash
pip install httpx
# create a device (prints device_secret + claim_code)
python tools/simulator.py provision SX-0001
# after claiming it in the app, start walking + press SOS after 60 s
python tools/simulator.py run SX-0001 <device_secret> --interval 5 --sos-after 60
```

## 3. Android app

1. Open the `android/` folder in **Android Studio** (it downloads Gradle and libraries on first sync).
2. Run on the **emulator** → server address `http://10.0.2.2:8000` (default).
   On a **real phone** → use your computer's LAN IP, e.g. `http://192.168.1.20:8000` (same Wi-Fi), entered on the login screen.
3. Create an account → **Add tracker** → enter the Device ID + claim code from the simulator.
4. Start the simulator → the device moves on the map → after `--sos-after` seconds you get a **full-screen SOS alert** with Call 112, Navigate, Share, "I'm on it" and "Child is safe".

Screens in Phase 1: Login/Register · My family (devices, battery, online, SOS badge) · Add tracker · Live map + history trail (1 h / 6 h / 24 h / 7 days) + share with family · SOS emergency screen.

> Phase 1 uses a background WebSocket service for alerts. Phase 2 adds Firebase Cloud Messaging so alerts arrive even when Android stops the app.

## 4. Firmware (ESP32-S3 + EG800K)

Needs **ESP-IDF v5.2+**.

```bash
cd firmware
cp main/secrets.h.example main/secrets.h     # device ID, secret, server URL, APN, SOS SMS numbers
idf.py set-target esp32s3
idf.py build flash monitor
```

What it does: wake (timer / SOS button / motion) → SOS hold 1.5 s → silent vibration → modem on → network + data → GNSS fix → POST telemetry → follow server's report interval → modem fully off → deep sleep. During SOS it reports every 10 s until the family marks the child safe; if data fails it sends **SMS with the last location**.

⚠️ Before production, verify against Quectel documents (marked `NOTE/TODO` in code): EG800K PWRKEY timing, HTTP(S) AT commands, SSL certificate setup, GNSS AT command format. Also check the LIS2DW12 I²C address (SA0) on the PCB.

## 5. Device ↔ server protocol

`POST /api/device/telemetry` with headers `X-Device-Id`, `X-Device-Secret`:

```json
{"t":1760000000,"lat":12.9716,"lon":77.5946,"acc":8,"spd":4.5,"hdg":90,"bat":82,"chg":0,"sos":0,"fw":"1.1.0"}
```
Reply: `{"ok":true,"interval_s":300,"sos_active":false}` (10 s during SOS, 60 s when moving fast, 300 s normally).
Same JSON (plus `"secret"`) can be published over MQTT to `selfx/<device_id>/telemetry`.

## 6. Security notes (before launch)
- Change `SELFX_JWT_SECRET` and `SELFX_ADMIN_KEY`; use HTTPS + TLS MQTT; set Android `cleartextTrafficPermitted="false"`.
- Children's location data → parental consent (DPDP Act), data stored in India, retention policy.

## 7. Phase 2 features (now included)

| Feature | Where in the app | Notes |
|---|---|---|
| **Safe zones** (home / school / tuition) | Map screen → 🏠 icon | Move map, set radius, add. Alerts "✅ Riya reached School" / "Riya left Home" |
| **Offline alert** | automatic | Tracker silent for 30 min → family alerted; "back online" when it reconnects |
| **Live location link** | Map → 🔗 icon, and SOS screen | Web page anyone can open (no app). Expires (30 min–8 h); SOS links stop automatically when "Child is safe" is pressed |
| **School safety circle** | My family → 🏫 icon | Principal registers school → gets **staff code** + **parent code**. Teachers/security/bus staff join with staff code. Parents link a tracker (Map → ⋮ → Link to school) = consent. Staff get SOS alerts + "Student SOS board" (location only during an active SOS) |
| **Emergency info pack** | SOS alerts, school board, live page | Speed, heading, battery, last update, accuracy |
| **Push notifications (Firebase)** | automatic once configured | Alerts arrive even when the app is closed (see below) |

### Live link address
Links use `SELFX_PUBLIC_BASE_URL` (default `http://localhost:8000`, only works on your Mac).
For links that work on any phone, deploy the server online and set e.g. `SELFX_PUBLIC_BASE_URL=https://api.yourdomain.in`.

### Push notifications (Firebase) – optional but recommended
1. https://console.firebase.google.com → **Add project** (e.g. SelfXTrack).
2. **Add app → Android**, package name `com.selfxtrack.app` → you get the values for step 3 (you can skip downloading google-services.json).
3. Copy `android/firebase.properties.example` → `android/firebase.properties` and fill `apiKey`, `appId`, `projectId`, `senderId` (Project settings → General → Your apps). Rebuild the app.
4. Server: Project settings → **Service accounts → Generate new private key** (JSON). Then:
   ```bash
   pip install firebase-admin
   export SELFX_FCM_CREDENTIALS=/path/to/service-account.json
   ```
   restart the server. Without these, the app still works using its live connection (alerts only while the app's service runs).

### Try Phase 2 with the simulator
1. Map → 🏠 → add a safe zone around the simulator route (Bengaluru, e.g. "Home", 200 m) → watch enter/exit alerts.
2. Map → 🔗 → create a 30-min link → open it in your Mac browser.
3. 🏫 → Register a school → note codes → create a 2nd account (teacher) → Join as staff with the staff code → back on the parent account: Map → ⋮ → Link to school (parent code). Run the simulator with `--sos-after 30` → teacher account gets "🚨 Student SOS".
4. Stop the simulator for 30+ min (or set `SELFX_OFFLINE_AFTER_MINUTES=2`) → offline alert.

## 8. Phase 3 (now included)
- **Phone OTP** for every account (dev mode: code is printed in the server console and shown in the app).
- **Child SOS → parents first**; school is auto-alerted after 300 s if no parent responds.
- **Emergency – School / Emergency – Group** (Smart/Guardian plans): Map screen and SOS screen. Group = verified SelfXTrack users within 1 km (2 km after 2 min); they see distance only until they tap "I can help".
- **School SOS board** lists every student who pressed SOS; Guardian plan shows **👥 Emergency – Group** on each row.
- **Teacher contacts** (Map → ⋮): up to 5, get SMS + live link on school escalation.
- **Help nearby** toggle (My family → 💜 icon), report/ban (3 reports = auto-ban), location access log.
- Change a plan (testing): `POST /api/admin/users/plan` with header `X-Admin-Key`.

## 9. Phase 4 (now included) – AI + plans + payments
| Feature | Where | Plan |
|---|---|---|
| Route learning (usual places + corridor from 21 days) | Map → ✨ Insights | Smart+ |
| Unusual route / unfamiliar stop alerts (advisory, never SOS) | push notification | Smart+ |
| Smart ETA from learned trips: "Home by 15:12 (~9 min) · usually 25 min" – destination predicted (Home / School / Tuition) | Insights | Smart+ |
| Late arrival · didn't leave on time · missed usual place alerts | push | Smart+ |
| Per-trip route: left the usual School→Home route · usual road at unusual time · vehicle speed when he usually walks · stopped 10+ min on the way | push | Smart+ |
| Holidays: 🏖 button (today / vacation dates, all children) + gentle "Holiday today?" question instead of alarms; holidays not learned | Insights | Smart+ |
| Daily summary (today / yesterday) | Insights | Smart+ |
| Assistant: "Where was Riya at 4 pm?" – answers only from data | Insights | Smart+ |
| Risk prompt: fast + off-route + after 8 pm → "Check on Riya?" | push | Guardian |
| Incident report (timeline for police / school, shareable) | SOS screen | Guardian |
| Plans Basic ₹199 / Smart ₹299 / Guardian ₹499 (yearly ₹1,999/2,999/4,999) | My family → 🏅 | – |
| Limits: history 7/30/30 days (30-day calendar on Smart+), family 2/5/8 | server | – |

- Alerts start after **5 days** of data (`SELFX_AI_MIN_DAYS`). Name places by adding safe zones (Home, School).
- **AI agent (Ask):** `backend/app/agent.py` – read-only tools (current_status, eta_to, day_timeline, place_visits, alerts, travel_stats, routine, location_at). Works with **any LLM**: Claude (`SELFX_ANTHROPIC_API_KEY`), or any OpenAI-compatible API – OpenAI, Gemini, Groq, OpenRouter, or **free local Ollama** (`SELFX_LLM_BASE_URL=http://localhost:11434/v1 SELFX_LLM_MODEL=llama3.1`). No key → local multi-step planner (week ranges, comparisons, multi-part questions).
- **Claude API (optional):** `SELFX_ANTHROPIC_API_KEY=...` makes summaries / answers more natural. Without it, template text from the same data is used.
- **Payments:** without keys = test mode (confirm in app). Real: set `SELFX_RAZORPAY_KEY_ID`, `SELFX_RAZORPAY_KEY_SECRET`, `SELFX_RAZORPAY_WEBHOOK_SECRET`, `SELFX_RAZORPAY_PLAN_IDS='{"smart_monthly":"plan_..."}'`, and point the Razorpay webhook to `/api/billing/webhook`.
- Payment fails → 7-day grace → Basic. **SOS always works.**

## 10. Phase 5 (now included)
| Feature | Where | Test with the simulator |
|---|---|---|
| **Parent / Family role** – parents ring at once, family after 2 min | Child setup → Family → Add / Make parent | `--sos-after 30` |
| **Indian public holidays** pause routine alerts (switchable) | Insights → 🏖 | – |
| **Weekly report** (Sunday 19:00 push) + 📊 button | Insights → 📊 | – |
| **Battery prediction** “will run out ~19:30” | Insights card + push | `--drain 2` |
| **School web dashboard** – students, SOS board, live map, call parent, 30-day history, alarm sound | `http://<server>:8000/school` | – |
| **Elderly: fall detection** (30 s cancel on device) → 🆘 POSSIBLE FALL SOS | Child setup (kind elderly) | `--fall-after 30` |
| **Elderly: no-movement alert** (N hours in a day window, Guardian) | Child setup → Elderly care | `--still` |
| **School bus BLE check-in** – boarded / got off | Child setup → School bus | `--bus BUS-12 --board-after 20 --alight-after 80` |
| **OTA firmware updates** – staged rollout, SHA-256, rollback, never during SOS / low battery | `/admin → Firmware` | `--fw 1.1.0` |

## 11. Phase 6 – production readiness (now included)
- `/admin` web panel (admin key): overview, users (plan, ban), trackers (firmware channel, OTA status), firmware releases, abuse reports.
- `SELFX_ENV=production` refuses to start with unsafe settings (default secrets, OTP dev mode, SQLite, `*` CORS, http).
- Rate limiting on login / register / OTP / password, security headers, deleted-account tokens rejected.
- DPDP: consent at sign-up, **Download my data** + **Delete my account** (app → 👤), daily retention clean-up (locations 90 days), `/privacy` + `/terms` drafts (lawyer review needed).
- `docker-compose.prod.yml` + Caddy (auto HTTPS) + `deploy/env.production.example` + `deploy/backup.sh` + `deploy/DEPLOY.md`.

## Roadmap
| Phase | Features |
|---|---|
| **1 ✅** | Location, SOS, family alerts, map, history, sharing, low-battery alert, SMS fallback |
| **2 ✅** | Firebase push, safe zones, offline alert, live link, school circle, emergency info pack |
| **3 ✅** | Community "Request Help": verified helpers, progressive location disclosure, helper tracking |
| **4 ✅** | AI (route learning, unusual route/stop, ETA, summaries), Basic/Smart/Guardian plans, Razorpay |
| **5 ✅** | Parent role, holidays, weekly report, battery prediction, school web dashboard, BLE bus check-in, elderly fall/inactivity, OTA updates |
| **6 ✅ (software)** | Admin panel, production checks, rate limits, DPDP export/delete/retention, Docker + HTTPS deploy |
| Next | Real-hardware test, keys (Firebase, SMS, Razorpay, LLM), cloud deploy, Play Store, iOS app |
