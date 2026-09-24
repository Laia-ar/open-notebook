import os

# ROOT DATA FOLDER
DATA_FOLDER = "./data"

# LANGGRAPH CHECKPOINT FILE
sqlite_folder = f"{DATA_FOLDER}/sqlite-db"
os.makedirs(sqlite_folder, exist_ok=True)
LANGGRAPH_CHECKPOINT_FILE = f"{sqlite_folder}/checkpoints.sqlite"

# UPLOADS FOLDER
UPLOADS_FOLDER = f"{DATA_FOLDER}/uploads"
os.makedirs(UPLOADS_FOLDER, exist_ok=True)

# PODCASTS FOLDER
# Matches the root that build_episode_output_dir() (commands/podcast_commands.py)
# creates episode directories under when called with DATA_FOLDER in production.
PODCASTS_FOLDER = f"{DATA_FOLDER}/podcasts"
os.makedirs(PODCASTS_FOLDER, exist_ok=True)

# TIKTOKEN CACHE FOLDER
# Reads TIKTOKEN_CACHE_DIR from the environment so Docker can redirect the cache
# to a path outside /data/ (which is typically volume-mounted and would hide the
# pre-baked encoding baked into the image at build time).
TIKTOKEN_CACHE_DIR = os.environ.get("TIKTOKEN_CACHE_DIR", "").strip() or f"{DATA_FOLDER}/tiktoken-cache"
os.makedirs(TIKTOKEN_CACHE_DIR, exist_ok=True)

# Google OAuth
GOOGLE_CLIENT_ID = "806319341743-p69igv4v2rfph29lic07ov2p0ipufct5.apps.googleusercontent.com"
_GOOGLE_REDIRECT_URI_DEFAULT = "http://localhost:5055/api/auth/google/callback"
_google_redirect_uri_env = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()

# Solo usamos el valor del .env si tiene forma de URL válida y termina en la
# ruta esperada. Si está vacío, mal escrito o incompleto (como pasó en el
# servidor: "http://64.176.11.56:8503" sin la ruta del callback), caemos al
# valor hardcodeado en vez de mandarle ese valor roto a Google.
if _google_redirect_uri_env.startswith(("http://", "https://")) and _google_redirect_uri_env.endswith(
    "/api/auth/google/callback"
):
    GOOGLE_REDIRECT_URI = _google_redirect_uri_env
else:
    GOOGLE_REDIRECT_URI = _GOOGLE_REDIRECT_URI_DEFAULT

OPEN_NOTEBOOK_FRONTEND_URL = os.environ.get(
    "OPEN_NOTEBOOK_FRONTEND_URL",
    "http://localhost:3000",
).strip()

OPEN_NOTEBOOK_SESSION_DAYS = int(
    os.environ.get("OPEN_NOTEBOOK_SESSION_DAYS", "30")
)

OPEN_NOTEBOOK_COOKIE_SECURE = (
    os.environ.get("OPEN_NOTEBOOK_COOKIE_SECURE", "false").lower() == "true"
)

# Dominio de email permitido
NOTEBOOK_SHARE_ALLOWED_DOMAIN = os.environ.get(
    "NOTEBOOK_SHARE_ALLOWED_DOMAIN", "laia.com.ar"
).strip().lower()
