# Runs before any test module is imported: always use a throw-away database, never the dev selfx.db.
import os
import tempfile

os.environ["SELFX_DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test_selfx.db")
os.environ["SELFX_ADMIN_KEY"] = "test-admin"
# tests never call a real AI model (backend/.env may contain a key)
os.environ["SELFX_LLM_PROVIDER"] = "none"
os.environ["SELFX_GEOCODER"] = "none"           # no internet lookups in tests
# many accounts are registered from one test client – the rate-limit test sets its own small limit
os.environ["SELFX_RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["SELFX_LLM_API_KEY"] = ""
os.environ["SELFX_ANTHROPIC_API_KEY"] = ""
