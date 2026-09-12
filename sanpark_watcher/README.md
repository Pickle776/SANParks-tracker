# SANParks Availability Watcher - Handoff Notes

## What this is

A Flask web app with a browser GUI. You pick a park, dates, and (optionally)
specific camps/accommodation types, set an ntfy.sh topic name and a check
interval, and it polls SANParks in the background. It only pings your phone
when something goes from "not available" to "available" - not on every
check.

## How to run it (right now, on Windows)

```
cd sanpark_watcher
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000` in a browser.

Leave that terminal window open - closing it stops the app (and any watches
with it, though they'll resume from where they left off next time you start
it, since watches.json and state/ persist to disk).

## How the pieces fit together

- **sanparks_api.py** - all direct communication with sanparks.org. One key
  function, `fetch_park_inventory()`, does double duty: it's used both to
  populate the GUI's camp/type checkboxes AND to actually check availability
  during a watch. That's possible because the API always returns the same
  full rolling-year dataset for a park regardless of what date range you ask
  for - we just parse the result differently depending on the purpose.
- **watch_manager.py** - the "brain." Each watch runs in its own background
  thread. Every poll, it saves the currently-open dates for that watch to a
  JSON file in `state/`, and compares against last time to figure out what's
  NEW. Only new openings trigger a notification.
- **notifier.py** - one function, POSTs to `https://ntfy.sh/<topic>`.
- **app.py** - Flask routes tying the GUI to the above.
- **templates/index.html** - the whole GUI, vanilla JS, no build step needed.

## Known working / already tested

- Cookie/session handling via curl_cffi with `impersonate="chrome"` - proven
  to get past Cloudflare in the original debugging session.
- The core availability-fetch-and-parse logic - this is a refactor of a
  script that was already confirmed working against real Augrabies data.
- `getParks.php` - confirmed working, returns all 19 parks.

## NOT yet tested - things to check first

1. **`/api/inventory` on a big park.** Augrabies has ~9 accommodation types
   in 1 camp. Kruger has a dozen+ camps and dozens of types. The pagination
   loop in `fetch_park_inventory()` (offset/limit) should handle this, but
   it's untested against a park that actually needs multiple pages. Test
   with Kruger (park id 26) first and watch app.py's console output for
   errors.
2. **Whether `resortno` is always present and stable.** The grouping logic
   assumes every item has a `resortno` and that it's a reliable "this camp"
   key. If any items come back without one, they'll all get lumped under a
   key called `"unknown"` - worth checking for that in the GUI when testing
   bigger parks.
3. **Session/cookie expiry during a long-running watch.** `get_session()`
   refreshes the cached session every 20 minutes, but this number is a
   guess, not measured. If watches start throwing 403s or 500s after running
   for hours, this TTL is the first thing to tune down. Cloudflare's
   `cf_clearance` cookie lifetime is what actually governs this - worth
   checking how long that cookie is valid for and matching the TTL to it.
4. **Concurrent watches hitting the API at the same time.** Right now every
   watch has its own thread and its own timer, so if someone sets up 3
   watches with the same interval they could all fire near-simultaneously.
   Not necessarily a problem, but worth keeping an eye on for rate-limiting
   from SANParks' side if this becomes a habit.

## Still to build

1. **Windows startup automation.** Currently you have to manually run
   `python app.py` and leave a terminal open. For "set it up and forget it,"
   this needs to run automatically:
   - Windows: Task Scheduler entry that runs `python app.py` at login /
     on a schedule, or a `.bat` file with a shortcut in the Startup folder.
   - Linux (the old laptop, in a couple months): a systemd service file so
     it starts on boot and restarts if it crashes.
2. **A "camp name" filter/search in the GUI for big parks.** Once Kruger's
   dozens of camps are all rendering as expanded checkboxes, the page will
   be very long. Consider a search box that filters the camp groups by
   name, or making each camp group collapsed by default (click to expand).
3. **Basic input validation in the GUI.** E.g. stopping someone from
   submitting a departure date before the arrival date, or an interval of 0.
4. **Nicer notification content.** Right now the ntfy message is a plain
   list of camp/unit/dates. Could add a direct booking link
   (`https://www.sanparks.org/reservations/accommodation/filters/parks/<park_id>/...`)
   so tapping the notification takes you straight to booking.
5. **Optional: "quiet hours"** so notifications don't fire at 3am (ntfy
   supports scheduled delivery, or this could just be handled by not
   polling during certain hours).
6. **Optional: multi-user support.** Right now all watches share one
   process/one machine. Fine for one household; if this ever needs to serve
   more than your dad, config/state would need per-user separation.
7. **Error resilience polish.** If SANParks returns a 500 or times out
   mid-poll, the current code logs it to `last_error` and tries again next
   interval - reasonable, but hasn't been stress-tested against a real
   outage.

## Files

```
sanpark_watcher/
  app.py              Flask routes
  sanparks_api.py      SANParks API wrapper
  watch_manager.py     Background watch threads + state diffing
  notifier.py          ntfy.sh push sender
  templates/index.html GUI
  requirements.txt
  watches.json         created automatically - active watch configs
  state/                created automatically - per-watch "last seen" data
```
