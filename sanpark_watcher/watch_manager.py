# watch_manager.py
"""
watch_manager.py

Manages "watches" - each one is: a park, a date range, an optional list of
specific camp/accommodation-type units to restrict to, an ntfy topic, and a
polling interval.

Each active watch runs in its own background thread. Every poll, it fetches
current availability, compares it against the last-saved state for that watch
(state/<watch_id>.json), and only sends a notification for dates that are
NEWLY open since the last check - not every open date every time.

Watches are persisted to watches.json so restarting the app can resume them.
"""

import json
import os
import threading
import uuid
from datetime import datetime

import sanparks_api
from notifier import send_ntfy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHES_FILE = os.path.join(BASE_DIR, "watches.json")
STATE_DIR = os.path.join(BASE_DIR, "state")

os.makedirs(STATE_DIR, exist_ok=True)

_lock = threading.Lock()
_threads = {}
_stop_events = {}
_watches = {}  # watch_id -> config dict


def _state_path(watch_id):
    return os.path.join(STATE_DIR, f"{watch_id}.json")


def _load_state(watch_id):
    path = _state_path(watch_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def _save_state(watch_id, state):
    with open(_state_path(watch_id), "w") as f:
        json.dump(state, f, indent=2)


def _save_watches():
    with open(WATCHES_FILE, "w") as f:
        json.dump(_watches, f, indent=2)


def _load_watches():
    global _watches
    if os.path.exists(WATCHES_FILE):
        with open(WATCHES_FILE, "r") as f:
            try:
                _watches = json.load(f)
            except json.JSONDecodeError:
                _watches = {}


def list_watches():
    with _lock:
        return [{**cfg, "id": wid, "running": wid in _threads} for wid, cfg in _watches.items()]


def create_watch(config):
    watch_id = str(uuid.uuid4())[:8]
    config["created"] = datetime.now().isoformat()
    config["last_checked"] = None
    config["last_error"] = None
    with _lock:
        _watches[watch_id] = config
        _save_watches()
    start_watch(watch_id)
    return watch_id


def delete_watch(watch_id):
    stop_watch(watch_id)
    with _lock:
        _watches.pop(watch_id, None)
        _save_watches()
    state_path = _state_path(watch_id)
    if os.path.exists(state_path):
        os.remove(state_path)


def start_watch(watch_id):
    with _lock:
        if watch_id in _threads:
            return
        config = _watches.get(watch_id)
        if not config:
            return
        stop_event = threading.Event()
        _stop_events[watch_id] = stop_event
        thread = threading.Thread(target=_run_watch_loop, args=(watch_id, stop_event), daemon=True)
        _threads[watch_id] = thread
        thread.start()


def stop_watch(watch_id):
    with _lock:
        stop_event = _stop_events.get(watch_id)
        if stop_event:
            stop_event.set()
        _threads.pop(watch_id, None)
        _stop_events.pop(watch_id, None)


def start_all_saved_watches():
    for watch_id in list(_watches.keys()):
        start_watch(watch_id)


def _run_watch_loop(watch_id, stop_event):
    while not stop_event.is_set():
        config = _watches.get(watch_id)
        if not config:
            return

        try:
            _check_once(watch_id, config)
            config["last_error"] = None
        except Exception as e:
            config["last_error"] = str(e)
            print(f"[{watch_id}] Error: {e}")

        config["last_checked"] = datetime.now().isoformat()
        with _lock:
            _save_watches()

        interval_minutes = config.get("interval_minutes", 10)
        stop_event.wait(interval_minutes * 60)


def _check_once(watch_id, config):
    target_start = datetime.strptime(config["arrival_date"], "%Y-%m-%d").date()
    target_end = datetime.strptime(config["departure_date"], "%Y-%m-%d").date()

    raw_items = sanparks_api.fetch_park_inventory(
        config["park_id"], config["park_name"], config["arrival_date"], config["departure_date"]
    )

    allowed_keys = None
    if config.get("units"):
        allowed_keys = {(u["resortno"], u["code"]) for u in config["units"]}

    current = sanparks_api.extract_open_dates(raw_items, target_start, target_end, allowed_keys)

    # Flatten tuple keys to strings so this is directly JSON-serializable
    current_serializable = {f"{resortno}|{code}": info for (resortno, code), info in current.items()}

    previous = _load_state(watch_id)

    new_openings = []
    for key, info in current_serializable.items():
        prev_dates = set(previous.get(key, {}).get("open_dates", {}).keys())
        new_dates = set(info["open_dates"].keys()) - prev_dates
        if new_dates:
            new_openings.append((info, new_dates))

    if new_openings:
        total_new_dates = sum(len(dates) for _, dates in new_openings)
        
        if total_new_dates == 1:
            info, dates = new_openings[0]
            date = list(dates)[0]
            message = f"{info['camp_name']} - {info['unit_name']}: {date}"
        else:
            message = "Multiple spots available. Check SANParks."

        send_ntfy(
            config.get("ntfy_topic", ""),
            title=f"SANParks Alert: {config['park_name']}",
            message=message,
            priority="high",
        )

    _save_state(watch_id, current_serializable)


_load_watches()