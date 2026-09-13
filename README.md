# README.md
# SANParks Availability Watcher

A background scraper and local web GUI that automatically monitors SANParks accommodation. It checks for new openings within your desired dates and sends a push notification only when a previously booked spot becomes available.

## Included Code
* `app.py`: The Flask web server that handles the frontend GUI and API routing.
* `sanparks_api.py`: Wraps the SANParks booking API to fetch and parse current availability arrays.
* `watch_manager.py`: Handles concurrent background polling, diffs new availability against saved states, and triggers external alerts.
* `notifier.py`: Delivers push notifications directly to a smartphone using ntfy.sh.

## Reliability & Environment Setup
This tool is built to run headless 24/7. When running on older hardware (such as a repurposed Linux Mint laptop), network and power instability can silently kill the scraper. The code supports the following external reliability measures, which you can interpret and configure for your own hardware:

* **Uptime Monitoring (Healthchecks.io):** The `watch_manager.py` script is designed to silently hit a Healthchecks ping URL once every minute. If the machine loses power or internet and misses its grace period, Healthchecks notifies you that the system is down.
* **Automated Error Alerts (ntfy.sh):** Push notifications handle successful spot-opening alerts, but will also fire a high-priority push if the scraper crashes or gets blocked by the host server. 
* **Self-Healing Wi-Fi (Cron):** To counter older Linux hardware dropping Wi-Fi connections indefinitely, it's recommended to run a root cron job watchdog that checks outbound connectivity (e.g., `ping -c 1 8.8.8.8`). If the ping fails, the watchdog forces the network adapter to cycle off and on via `nmcli`, keeping the machine online without physical intervention.
