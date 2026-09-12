"""
notifier.py

Sends push notifications via ntfy.sh - no account or API key needed.
The person just installs the ntfy app and subscribes to the same topic name
used here, and pushes to https://ntfy.sh/<topic> show up on their phone.
"""

import requests


def send_ntfy(topic, title, message, priority="default", tags=None):
    if not topic:
        print("No ntfy topic configured - skipping notification.")
        return

    headers = {
        "Title": title,
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = ",".join(tags)

    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
    except Exception as e:
        print(f"Failed to send ntfy notification: {e}")
