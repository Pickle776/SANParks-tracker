# app.py
"""
app.py

Flask app tying everything together:
  GET  /                    -> the GUI page
  GET  /api/parks           -> list of all parks (cached)
  GET  /api/inventory       -> camps + accommodation types for a chosen park
  GET  /api/watches         -> list of active watches + their status
  POST /api/watches         -> create + start a new watch
  DELETE /api/watches/<id>  -> stop + delete a watch

Run with: python app.py (or double-click start_watcher.bat)
"""

from flask import Flask, jsonify, render_template, request

import sanparks_api
import watch_manager

app = Flask(__name__)

_parks_cache = {"data": None}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/parks")
def api_parks():
    if _parks_cache["data"] is None:
        _parks_cache["data"] = sanparks_api.fetch_parks()
    return jsonify(_parks_cache["data"])


@app.route("/api/inventory")
def api_inventory():
    park_id = request.args.get("park_id")
    park_name = request.args.get("park_name")
    arrival = request.args.get("arrival")
    departure = request.args.get("departure")

    if not all([park_id, park_name, arrival, departure]):
        return jsonify({"error": "Missing park_id, park_name, arrival or departure"}), 400

    try:
        raw_items = sanparks_api.fetch_park_inventory(park_id, park_name, arrival, departure)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    grouped = sanparks_api.group_inventory_by_camp(raw_items)
    return jsonify(grouped)


@app.route("/api/watches", methods=["GET"])
def api_list_watches():
    return jsonify(watch_manager.list_watches())


@app.route("/api/watches", methods=["POST"])
def api_create_watch():
    body = request.get_json(force=True, silent=True) or {}

    required = ["park_id", "park_name", "arrival_date", "departure_date"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing field(s): {', '.join(missing)}"}), 400

    config = {
        "park_id": str(body["park_id"]),
        "park_name": body["park_name"],
        "arrival_date": body["arrival_date"],
        "departure_date": body["departure_date"],
        "units": body.get("units", []),  # [] means "watch everything in this park"
        "interval_minutes": int(body.get("interval_minutes", 10)),
        "ntfy_topic": body.get("ntfy_topic", "YOUR_NTFY_TOPIC"), # Set to user's desired topic
    }

    watch_id = watch_manager.create_watch(config)
    return jsonify({"id": watch_id})


@app.route("/api/watches/<watch_id>", methods=["DELETE"])
def api_delete_watch(watch_id):
    watch_manager.delete_watch(watch_id)
    return jsonify({"ok": True})


if __name__ == "__main__":
    watch_manager.start_all_saved_watches()
    app.run(host="0.0.0.0", port=5000, debug=False)
