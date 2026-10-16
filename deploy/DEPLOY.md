# Deploying SelfXTrack (production)

1. **Server in India** (DPDP): e.g. AWS Mumbai (ap-south-1) / Azure Central India – 2 vCPU, 4 GB RAM, Ubuntu 24.04.
   Install Docker. Point DNS `api.selfxtrack.in` → server IP. Open ports 80, 443 (and 1883/8883 only if trackers use MQTT).
2. `git clone` the project to `/opt/selfxtrack`, then
   `cp deploy/env.production.example .env.production` and fill every value.
   Put the Firebase service-account JSON in `./secrets/`.
3. `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build`
   The API **refuses to start** if a setting is unsafe (default secrets, OTP dev mode, SQLite, `*` CORS, http URL…) and prints what to fix.
4. Check: `https://api.selfxtrack.in/health`, `/docs` (consider hiding), `/school`, `/admin`, `/privacy`, `/terms`.
5. Backups: `crontab -e` → `0 2 * * * /opt/selfxtrack/deploy/backup.sh`; copy backups off-site. Test a restore.
6. Monitoring: uptime check on `/health` (e.g. UptimeRobot), disk alerts, `docker compose logs -f api`.
7. Android release: set the server address to `https://api.selfxtrack.in`, `cleartextTrafficPermitted=false`,
   release signing key, Play Console background-location declaration + privacy policy URL (`/privacy`).
8. Firmware: build with the production `SX_SERVER_URL` (https) + CA certificate (modem `seclevel 1`), sign images,
   upload new versions in **/admin → Firmware** with a 10 % rollout first.

Scaling later: run several API containers with `SELFX_RUN_MONITOR=false` on all but one, put Redis-based rate limiting
in front, and move AI learning to a worker. Database migrations: switch from the built-in `ensure_schema()` to Alembic
before the first schema change after launch.
