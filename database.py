import os, json, tempfile, threading
import config

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()

def save_json(path: str, data):
    dir_ = os.path.dirname(path) or "."
    os.makedirs(dir_, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        tmp = f.name
    os.replace(tmp, path)

def load_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        print(f"[database] JSON decode error in {path}: {e}", flush=True)
        return default

def _get_lock(filename: str) -> threading.Lock:
    with _locks_lock:
        if filename not in _locks:
            _locks[filename] = threading.Lock()
        return _locks[filename]

def load_state(filename: str, default: dict) -> dict:
    d = config.DATA_DIR()
    os.makedirs(d, exist_ok=True)
    with _get_lock(filename):
        return load_json(os.path.join(d, filename), default=default) or default

def save_state(filename: str, data: dict):
    d = config.DATA_DIR()
    os.makedirs(d, exist_ok=True)
    with _get_lock(filename):
        save_json(os.path.join(d, filename), data)
