# SANParks Availability Watcher

A background scraper and local web GUI that automatically monitors SANParks accommodation. It checks for new openings within your desired dates and sends a push notification only when a previously booked spot becomes available.

## Included Code
* `app.py`: The Flask web server that handles the frontend GUI and API routing.
* `sanparks_api.py`: Wraps the SANParks booking API to fetch and parse current availability arrays.
* `watch_manager.py`: Handles concurrent background polling, diffs new availability against saved states, and triggers external alerts.
* `notifier.py`: Delivers push notifications directly to a smartphone using ntfy.sh.

## Reliability & Environment Setup
This tool is built to run headless 24/7. When running on older hardware (such as a repurposed Linux laptop), network and power instability can silently kill the scraper. The setup incorporates several layers of self-healing and monitoring:

* **Uptime Monitoring (Healthchecks.io):** The `watch_manager.py` script silently pings a Healthchecks URL every minute. If the machine loses power, Wi-Fi, or crashes and misses its grace window, Healthchecks sends an alert that the host is down.
* **Automated Error Alerts (ntfy.sh):** Push notifications alert on open booking slots, but also fire a high-priority push notification if the scraper crashes or encounters upstream anti-scraping blocks.
* **Driver & Power-Management Stabilization:** Older wireless chips (such as Realtek PCIe adapters) often suffer from aggressive Linux kernel power-saving states (`fwlps`, `ips`, `aspm`) that put the radio transceiver into a deep sleep and freeze outbound traffic. Disabling driver-level power saving in `/etc/modprobe.d/` and disabling NetworkManager Wi-Fi power-saving keeps the radio active 24/7.
* **Static IP Architecture:** When running behind Wi-Fi range extenders or secondary access points where DHCP negotiation can time out, configuring a static IPv4 assignment ensures immediate, zero-timeout network association.
* **Smart Self-Healing Watchdog & AP Failover (Cron):** A scheduled background watchdog script runs every few minutes to safeguard connectivity:
  * Non-intrusive: Verifies NetworkManager is not actively in the middle of authenticating before acting, avoiding connection thrashing.
  * Multi-check: Confirms genuine loss of connectivity by probing both the local gateway and external DNS.
  * Automatic Failover: First attempts recovery on the primary Wi-Fi network (e.g., range extender); if the primary AP remains unreachable (such as a power cut to the extender), it automatically fails over to the secondary/main router SSID.
