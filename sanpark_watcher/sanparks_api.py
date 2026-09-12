"""
sanparks_api.py

Thin wrapper around the (undocumented) SANParks booking API.

Key discovery from manual debugging: getAvailabilityMatch.php ignores the
requested date range for WHICH records come back - it always returns every
accommodation type for the requested park(s), each with a rolling ~1 year
Availability array. This means one unfiltered call per park gives us:
  - every camp (resort) in that park
  - every accommodation type in each camp
  - a full year of day-by-day open-unit counts

So we don't need the separate getTypesByCampIDs.php / getFeaturesByTypeIDs.php
endpoints at all. One function does double duty: populating the GUI dropdowns
AND powering the actual watch/poll loop.
"""

import json
import time
from datetime import datetime

from curl_cffi import requests

BASE = "https://www.sanparks.org"
PARKS_URL = f"{BASE}/includes/SANParksApp/API/v1/bookings/accommodation/getParks.php"
AVAILABILITY_URL = f"{BASE}/includes/SANParksApp/API/v1/bookings/accommodation/getAvailabilityMatch.php"

# Cache a single curl_cffi session (with Cloudflare cookies) and refresh it
# periodically rather than re-visiting the homepage on every single request.
_session_cache = {"session": None, "created": 0.0}
SESSION_TTL_SECONDS = 20 * 60


def get_session():
    now = time.time()
    if _session_cache["session"] is None or (now - _session_cache["created"]) > SESSION_TTL_SECONDS:
        session = requests.Session(impersonate="chrome")
        # Visiting the homepage first lets Cloudflare hand out PHPSESSID / cf_clearance
        session.get(f"{BASE}/reservations/accommodation", timeout=15)
        time.sleep(1)
        _session_cache["session"] = session
        _session_cache["created"] = now
    return _session_cache["session"]


def fetch_parks():
    """Returns the raw list of {id, name} dicts for every SANParks park."""
    session = get_session()
    resp = session.get(PARKS_URL, headers={"accept": "application/json, text/plain, */*"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("STATUS") != "OK":
        raise RuntimeError(f"getParks.php returned non-OK status: {data.get('MESSAGE')}")
    return data.get("DATA", [])


def fetch_park_inventory(park_id, park_name, arrival_date, departure_date):
    """
    Calls getAvailabilityMatch.php for one park and pages through the results
    until exhausted. Returns the raw list of resort/accommodation-type dicts.

    arrival_date/departure_date must be YYYY-MM-DD strings. They can be
    basically any valid pair - the API returns the same rolling year of data
    regardless, so callers can reuse this for both "what camps/types exist"
    (GUI dropdown population) and "is anything open in MY date range" (the
    actual watch loop) - just parse the returned Availability arrays
    differently for each purpose.
    """
    session = get_session()
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-GB,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "origin": BASE,
        "referer": (
            f"{BASE}/reservations/accommodation/filters/parks/{park_id}/"
            f"arrivalDate/{arrival_date}/departureDate/{departure_date}/"
            f"camps/0/types/0/features/0"
        ),
    }

    model_dict = {
        "parks": [{"id": str(park_id), "name": park_name, "itemName": park_name}],
        "dates": "Check in - Check out",
        "arrival_date": arrival_date,
        "departure_date": departure_date,
        "camps": [],
        "types": [],
        "features": [],
    }

    all_items = []
    offset = 0
    limit = 50  # bigger page size than the site's default 12, to reduce round trips

    while True:
        payload = {
            "model": json.dumps(model_dict, separators=(",", ":")),
            "l": limit,
            "o": offset,
        }
        resp = session.post(AVAILABILITY_URL, headers=headers, data=payload, timeout=25)
        resp.raise_for_status()
        data = resp.json()

        if data.get("STATUS") != "OK":
            raise RuntimeError(f"getAvailabilityMatch.php returned non-OK status: {data.get('MESSAGE')}")

        page = data.get("DATA", {}).get("resort", [])
        if not isinstance(page, list):
            page = []

        all_items.extend(page)

        if len(page) < limit:
            break
        offset += limit

        # Safety valve - don't loop forever if something unexpected happens
        if offset > 2000:
            break

    return all_items


def group_inventory_by_camp(raw_items):
    """
    Groups the raw accommodation-type list into a structure the GUI can render:

    {
      "<resortno>": {
        "camp_name": "Augrabies Falls Rest Camp",
        "types": [
          {"code": "CK6P", "name": "CAMP SITE", "desc": "CK6P (CAMP SITE)",
           "typeno": "330", "rate": "362.00"},
          ...
        ]
      },
      ...
    }
    """
    camps = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        resortno = item.get("resortno", "unknown")
        camp_name = item.get("camp_name", "Unknown Camp")
        camps.setdefault(resortno, {"camp_name": camp_name, "types": []})
        camps[resortno]["types"].append(
            {
                "code": (item.get("sub_unitcode") or "").strip(),
                "name": (item.get("sub_unitname") or "").strip(),
                "desc": (item.get("accommodationtypedesc") or "").strip(),
                "typeno": item.get("accommodationtypeno", ""),
                "rate": item.get("adult_min_rate", ""),
            }
        )
    return camps


def extract_open_dates(raw_items, target_start, target_end, allowed_keys=None):
    """
    Parses each item's Availability array and returns only the dates that:
      - fall within [target_start, target_end)
      - have a unit count > 0
      - belong to a (resortno, sub_unitcode) pair in allowed_keys, if given

    Returns: { (resortno, sub_unitcode): {"camp_name", "unit_name", "park_name",
                                           "open_dates": {"YYYY-MM-DD": count, ...}} }
    """
    results = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        resortno = item.get("resortno", "")
        unit_code = (item.get("sub_unitcode") or "").strip()
        key = (resortno, unit_code)

        if allowed_keys and key not in allowed_keys:
            continue

        open_dates = {}
        for day_status in item.get("Availability", []):
            if "_" not in day_status:
                continue
            date_part, count_part = day_status.split("_", 1)
            try:
                current_date = datetime.strptime(date_part, "%Y-%m-%d").date()
            except ValueError:
                continue

            if target_start <= current_date < target_end and count_part.isdigit() and int(count_part) > 0:
                open_dates[date_part] = int(count_part)

        if open_dates:
            results[key] = {
                "camp_name": item.get("camp_name", ""),
                "unit_name": (item.get("sub_unitname") or "").strip(),
                "park_name": item.get("park_name", ""),
                "open_dates": open_dates,
            }

    return results
