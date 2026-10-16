from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SELFX_", extra="ignore")

    # Database: SQLite for local dev, PostgreSQL in production
    # e.g. postgresql+psycopg://selfx:selfx@db:5432/selfx
    database_url: str = "sqlite:///./selfx.db"

    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 60 * 24 * 30

    # Admin key used to provision new devices (factory / test jig)
    admin_key: str = "change-me-admin-key"

    # MQTT bridge (optional). Devices publish to selfx/<device_id>/telemetry
    mqtt_enabled: bool = False
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None

    # Firebase service-account JSON path (enables push notifications)
    fcm_credentials: str | None = None
    # Public base URL used in live share links, e.g. https://api.selfxtrack.in
    public_base_url: str = "http://localhost:8000"

    # OTP: "dev" logs the code on the server console and returns it to the app (testing only).
    # Production: "msg91" / "twilio" (add API keys) and set otp_dev_mode=false.
    sms_provider: str = "dev"
    otp_dev_mode: bool = True

    # Plans: features by plan (decision D2). Dev default plan for new users (set "basic" in production).
    default_plan: str = "guardian"
    sos_family_escalation_seconds: int = 120   # child SOS: parents first, other family after 2 min
    sos_school_escalation_seconds: int = 300   # D5: then school after 5 min
    group_radius_m: int = 1000                  # D8
    group_expand_radius_m: int = 2000
    group_expand_after_seconds: int = 120
    helper_location_max_age_minutes: int = 30

    # ---- Phase 4: AI ----
    # Claude API (optional) – only writes summaries / answers from verified data. Without a key,
    # template text is used. Safety alerts never depend on it.
    # Any LLM provider (all optional):
    #   llm_provider = "anthropic"  -> Claude (anthropic_api_key / anthropic_model)
    #   llm_provider = "openai"     -> any OpenAI-compatible API: OpenAI, Google Gemini, Groq, Together,
    #                                  OpenRouter, Azure, or a FREE local model with Ollama (no key).
    #                                  set llm_base_url, llm_api_key, llm_model
    geocoder: str = "nominatim"                # place names for locations: nominatim / none
    llm_provider: str | None = None            # auto: anthropic if anthropic_api_key, else openai if llm_base_url/key
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    local_timezone: str = "Asia/Kolkata"
    ai_learn_days: int = 21            # history used for route learning
    ai_min_days: int = 5               # need this many days of data before unusual-route alerts
    ai_offroute_points: int = 2        # consecutive off-route reports before alerting
    ai_unknown_stop_minutes: int = 20
    ai_alert_cooldown_minutes: int = 30

    # ---- Phase 4: plans + Razorpay ----
    # Without keys, billing runs in "dev" mode (test checkout confirmed in the app).
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    # Razorpay plan IDs, e.g. {"smart_monthly":"plan_X","smart_yearly":"plan_Y",...}
    razorpay_plan_ids: dict[str, str] = {}
    grace_days: int = 7

    # ---- Phase 6: production ----
    env: str = "development"                 # set "production" on the server -> unsafe settings refuse to start
    cors_origins: str = "*"                  # production: e.g. "https://selfxtrack.in"
    run_monitor: bool = True                 # only ONE server instance should run the background monitor
    location_retention_days: int = 90        # DPDP: delete old location history
    log_retention_days: int = 180            # access logs / alerts
    trusted_proxies: str = ""                # IPs of our reverse proxy (Caddy), e.g. "172.18.0.1"; X-Forwarded-For only from these
    rate_limit_per_minute: int = 30          # per IP on login / register / OTP / password endpoints
    terms_version: str = "2026-10"

    low_battery_percent: int = 15
    offline_after_minutes: int = 30


settings = Settings()


def production_problems(s: Settings) -> list[str]:
    """Settings that are fine for development but dangerous in production."""
    bad = []
    if s.jwt_secret.startswith("change-me") or len(s.jwt_secret) < 32:
        bad.append("SELFX_JWT_SECRET must be a long random string (32+ chars)")
    if s.admin_key.startswith("change-me") or len(s.admin_key) < 24:
        bad.append("SELFX_ADMIN_KEY must be a long random string (24+ chars)")
    if s.otp_dev_mode or s.sms_provider == "dev":
        bad.append("OTP dev mode is on – set SELFX_OTP_DEV_MODE=false and a real SELFX_SMS_PROVIDER")
    if s.default_plan != "basic":
        bad.append("SELFX_DEFAULT_PLAN should be basic in production")
    if s.database_url.startswith("sqlite"):
        bad.append("Use PostgreSQL in production (SELFX_DATABASE_URL)")
    if s.cors_origins.strip() == "*":
        bad.append("Restrict SELFX_CORS_ORIGINS to your domain")
    if not s.public_base_url.startswith("https://"):
        bad.append("SELFX_PUBLIC_BASE_URL must be https://")
    return bad
