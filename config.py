# config.py at the standalone project root
import os

# Root of this standalone project (the folder containing this file).
PROJECT_SOURCE_ROOT = os.path.dirname(os.path.abspath(__file__))
BASE_LOG_FOLDER = os.path.join(PROJECT_SOURCE_ROOT, "log_files")
PROJECT_TEMP_PATH = os.path.join(PROJECT_SOURCE_ROOT, "temp")

# Local secrets file used by the (vault-free) credential skill. See core/skills/hashicorp.py
LOCAL_SECRETS_FILE = os.path.join(PROJECT_SOURCE_ROOT, "secrets", "local_secrets.json")
