# SelfXTrack – roadmap (written 15 Oct 2026)

Three steps, in this order. Each step lists **what**, **why**, **how** (design + files), **tests** and **done when**.
Code references are to the state of the project on 15 Oct 2026.

| Step | What | Size | Blocks launch? |
|---|---|---|---|
| 1 | "✅ It's OK" on route alerts + "Pause route alerts" switch | small (1–2 days) | **✅ done 15 Oct 2026** |
| 2 | Launch readiness: hardware, SMS, security, translations | large (2–4 weeks) | **yes** |
| 3 | After first real users: Plans, friend pairing, smarter route learning | medium each | no |

---

## Step 1 – Fewer unwanted route alerts  ✅ DONE (15 Oct 2026)

**As built:** server `ai.py` (`ROUTE_KINDS`, `route_paused`, `_end_trip_pause`, `learn_now`, `RouteModel.extra_cells`),
`POST/DELETE /api/devices/{id}/route-ok` (`routers/phase4.py`), pause state in `GET /api/devices/{id}/now`;
app: notification buttons "✅ It's OK" / "✅ Regular route" (`live/Notifier.kt`, `live/RouteOkReceiver.kt` – work with
the app closed), one "⏸ Pause route alerts" button on the child's map screen (`ui/MapScreen.kt`) → dialog: "Only the current trip"
(names the trip: "Left Swimming at 20:20, heading to Home"; shown only while the child is travelling – `trip` in
`GET /now`; + "regular route – remember it") or "For a time" with a slider 15 min – 8 h; while paused a one-line
"paused until … · Resume" bar; API accepts `minutes` (15–480); texts in 13 languages; tests `backend/tests/test_route_ok.py`.
**Added 15 Oct 2026 – new destination (School → Swimming instead of Home):** the Places schedule beats the learned
guess (`ai._scheduled_trip`: a slot starting within 90 min of leaving → no "unusual route" / "late" for that trip);
heading clearly to another saved place → that place is the destination (`ai._approaching_place`); "unusual route" and
"different way" are sent at most once per trip; no "didn't reach Home" while the child is at one of their places;
"It's OK" / pause also cover `late` and `missed`. Test: `backend/tests/test_new_destination.py`.
*Difference from the plan below:* the in-app buttons are on the **map screen** instead of the Insights alert list
(the Insights screen does not show the alert list yet).


### Why
Route learning (`backend/app/ai.py`, `learn()` / `check()` / `check_routine()`) correctly flags any road the child has not
used before. A party, a doctor visit or a trip with grandpa therefore produces *unusual route*, *unfamiliar stop* and
sometimes *didn't leave / missed place* alerts. Parents who get pointless alerts start ignoring the app – and then miss
the real one. One tap must be enough to say "this trip is fine".

### 1a. "✅ It's OK – I know" on the alert
**Behaviour**
- Route-type alerts (`route`, `detour`, `stop`, `linger`, `time`, `speed`) get two actions: **✅ It's OK** and **📍 Open map**.
- "It's OK" mutes these alert kinds **for this trip only**: until the child is inside one of their places again, or at most
  **3 hours**, whichever comes first.
- Optional checkbox in the confirmation: **"This is a regular route – learn it"** → the cells of this trip are added to the
  usual corridor immediately (no need to wait until it was seen on 2 days).
- **Never muted:** SOS, fall, offline, low battery, `sched_late` / `sched_early` (Places schedules), `risk` (night check).

**Server (backend/app)**
- `models.Device`: add `route_ok_until: DateTime | None`, `route_ok_by: int | None` (user id).
- `ai.py`:
  - `_alert()`: for the kinds listed above, `return` early when `dev.route_ok_until` is in the future.
  - At each telemetry report (`check()`): if the child is inside a known place (`places.is_at` for any place) and
    `route_ok_until` is set → clear it (trip over).
  - `learn_now(db, dev, since)` – helper that adds the cells visited since `since` to `RouteModel.cells` (used by
    "learn it").
- New endpoint in `routers/phase4.py`:
  `POST /api/devices/{id}/route-ok {"learn": bool}` → sets `route_ok_until = now + 3 h`, `route_ok_by = user`,
  optionally calls `learn_now()`. Returns `{"until": "HH:MM"}`.
- Tell the other family members (WebSocket + push type `route_ok`): *"saurav marked babai's trip as OK."*
- Logs: keep an `AiAlert(kind="route_ok")` row so the Insights list shows who silenced what and when.

**App (android)**
- `live/Notifier.kt`, branch `"ai_alert"`: for the kinds above add notification actions **It's OK** and **Open map**
  (a `BroadcastReceiver` calls the endpoint; "Open map" opens `map/{id}`).
- `ui/InsightsScreen.kt`: in the alert list, the latest route alert of an active trip shows the same **It's OK** button.
- After tapping: snackbar *"Route alerts paused for this trip (until 19:05)."*
- New texts via `t("…")` + all 12 translation tables (`i18n/`), and the two server texts in `push_msgs.py` /
  `push_msgs_tr.py`.

### 1b. "Pause route alerts" switch
- On the child's map screen (`ui/MapScreen.kt`): chip **"⏸ Pause route alerts: 1 h / 2 h / 4 h"**.
- Same server field and endpoint: `POST /api/devices/{id}/route-ok {"hours": 2}` (max 8 h).
- While paused the chip shows **"Route alerts paused until 18:30 · Resume"**; resume = `DELETE /api/devices/{id}/route-ok`.
- Ends automatically – a parent can never forget to switch alerts back on.

### Tests (backend/tests/test_route_ok.py)
- Unusual route → alert; after `route-ok` the same off-route reports → no alert; SOS during the pause → still SOS.
- Child enters a known place → pause cleared → next unusual route alerts again.
- Pause expires after 3 h (simulate `now`).
- `learn: true` → the trip's cells count as usual → no alert on the same route the next day.
- `sched_late`, `offline`, `low_battery` still fire while paused.

### Done when
- One tap on the notification stops further route alerts for that trip, on every family member's phone.
- Nothing safety-critical can be paused; every pause ends by itself.
- All tests green; texts in 13 languages.

---

## Step 2 – Launch readiness (must be done before real families use it)

### 2a. Hardware bring-up (firmware/)
| Item | File | Check |
|---|---|---|
| Modem AT commands (HTTP, SSL, file upload) | `main/modem.c` | Quectel EG800K: `AT+QFUPL`, `AT+QSSLCFG` (cacert, seclevel 1), `AT+QHTTPPOST/GET` really work |
| Certificate check | `main/ca_cert.h`, `ssl_setup()` | connection to the real server succeeds; a server with another certificate is **refused** |
| GNSS | `main/gnss.c` | fix time, accuracy, cold/warm start, indoor fallback |
| Fall detection | `main/accel.c` | tune thresholds with real drops vs. jumping / running; 30 s cancel works |
| BLE beacons | `main/ble.c` | boarded / got-off with a real beacon on a bus |
| Signed OTA | `sdkconfig.defaults` | generate the key (`espsecure.py generate_signing_key --version 2 --scheme rsa3072`), keep it offline; an unsigned image is **refused** |
| Battery | `main/power.c` | real battery life per report interval (10 s SOS / 60 s moving / 300 s idle) |
| SMS fallback | `main.c send_sos_sms()` | SOS by SMS when there is no data |

### 2b. SMS provider (backend/app/sms.py)
- Pick an Indian provider (MSG91, Gupshup, Twilio India, Exotel) and register **DLT**: entity, sender ID, and one
  template per message **per language** (OTP, school/place emergency SMS with live link).
- Implement `send_sms()` for the provider; settings `SELFX_SMS_PROVIDER`, keys and template IDs in `.env`.
- Turn off test mode in production: `SELFX_OTP_DEV_MODE=false` (the server refuses to start in production otherwise).
- Test: OTP arrives; emergency SMS with the live link arrives at a teacher / coach number.

### 2c. Remaining security items
| Item | Fix |
|---|---|
| Login tokens live 30 days, cannot be revoked | short access token (1 h) + refresh token; `token_version` on `User`, bumped on logout / password change |
| WebSocket token in the URL | send the token as the first WebSocket message instead (`routers/ws.py`, `live/AlertService.kt`) |
| One shared admin key | admin user accounts with 2-factor login + an audit log table of every admin action |
| Share-by-email gives access without consent | same invite → accept flow as family invites |
| Child locations not encrypted at rest | encrypted disk / managed PostgreSQL with encryption; daily encrypted backups (`deploy/backup.sh`) |
| No real DB migrations | introduce Alembic; first migration = current schema |
| Production config | `SELFX_ENV=production`, firewall only 443 (+80 for the certificate), MQTT per `deploy/mosquitto.prod.conf` |
| Secrets | new random JWT secret + admin key; rotate the Groq key that was on the old laptop |

### 2d. Translations
- A native speaker per language checks `android/.../i18n/*.kt`, `backend/app/push_msgs_tr.py`,
  `backend/app/lang_answers*.py` – **SOS and emergency texts first**.
- Known spots: Marathi place endings ("शाळा कडे"), gendered verbs in Marathi / Gujarati bus messages.

### 2e. Pilot
- 1–2 schools, 20–50 families, 4 weeks. Measure: false-alarm rate per child per week, SOS response time,
  battery life, app crashes. Fix the top issues before a wider launch.

### Done when
- Tracker passes every hardware check above; SMS works with DLT templates; all security items closed;
  translations reviewed; pilot shows < 1 unwanted alert per child per week.

---

## Step 3 – After the first real users

Build these in the order parents ask for them during the pilot.

### 3a. Plans (party, outing, trip)
- Parent adds: title, place (map pin, reuse the Places editor), date + start/end time, optional host name + phone.
- During the plan window (± travel time): no route / stop / routine alerts while the child is heading to or from the
  plan place; instead **reached the party**, **left early**, **not there by start + 15 min**, **moved > 1 km away from
  the party**.
- Host = temporary caretaker: "Alert Riya's mother" button in the SOS screen, live link that **expires at the plan end**;
  host phone deleted 7 days after the plan.
- Server: new `Plan` table, `places.current_context()` checks active plans first; App: "🎉 Plans" section in Child setup.

### 3b. Friend pairing (Bluetooth)
- Two children hold their trackers together and double-press within 30 s; BLE signal strength proves they are < 30 cm
  apart; both trackers send a one-time pairing code to the server.
- Both parents get a request ("Babai wants to be friends with Riya – accept?") with **no phone numbers**; only after
  both accept, each parent chooses to share their number. Remove any time.
- Optional extras: "Babai is with Riya", friend's parent as trusted contact in the SOS ladder. No location sharing
  between families by default.
- Firmware needs BLE advertising (today the tracker only scans).

### 3c. Smarter route learning
- Map-match to real roads (OSRM / Valhalla) instead of 165 m grid cells – fewer false alarms on parallel lanes.
- Weekday-specific routes (Wednesday tuition route).
- With data from many children: a model that scores how unusual a trip is, to cut false alarms further.

### 3d. Other ideas from the report (docs/SelfXTrack_Implementation_Report.docx, section 7)
Two-way voice call, silent SOS, indoor positioning (Wi-Fi / cell), attendance from school geofence, pickup
authorisation, iOS app, smartwatch / widget alerts, school & old-age-home dashboards.
