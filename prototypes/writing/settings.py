"""Read local .env without shell execution or secret logging."""
import os
from pathlib import Path

def load_env(path):
    path = Path(path)
    if not path.exists(): return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        key, sep, value = line.partition('=')
        if not sep or not key.strip().replace('_', '').isalnum(): continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"): value = value[1:-1]
        os.environ.setdefault(key.strip(), value)

def model_config(role):
    prefix = 'WRITING_' + ('A' if role == 'FEEDBACK' else role)
    base = os.environ.get(prefix + '_BASE_URL') or os.environ.get('OPENROUTER_BASE_URL') or 'https://openrouter.ai/api/v1'
    key = os.environ.get(prefix + '_API_KEY') or os.environ.get('OPENROUTER_API_KEY', '')
    return base.rstrip('/'), os.environ.get(prefix + '_MODEL', ''), key
