"""Backend HTTP Client.

This module provides HTTP communication with the Backend API.
The WhatsApp Bot must communicate with the Backend only through HTTP.

Do NOT call any backend Python modules directly.
"""

import requests
import json

def send_message_to_backend(phone: str, message: str) -> str:
    """Send a message to the backend via HTTP POST.

    Parameters
    ----------
    phone : str
        The sender's phone number.
    message : str
        The message content.

    Returns
    -------
    str
        The reply text from the backend, or "Backend unavailable" on error.

    Behavior:
    - Sends POST http://localhost:8000/message
    - Request body: {"phone": "...", "message": "..."}
    - Returns only the "reply" field as string
    - On any error (offline, timeout, invalid JSON, HTTP error): returns "Backend unavailable"
    - Never throws exceptions
    """
    try:
        url = "http://localhost:8000/message"
        payload = {
            "phone": phone,
            "message": message
        }

        response = requests.post(
            url,
            json=payload,
            timeout=10  # 10 second timeout
        )

        # Check for HTTP errors
        response.raise_for_status()

        # Parse JSON response
        data = response.json()

        # Return the reply field
        if isinstance(data, dict) and "reply" in data:
            return str(data["reply"])
        else:
            return "Backend unavailable"

    except requests.exceptions.RequestException:
        # Covers: ConnectionError, Timeout, HTTPError, etc.
        return "Backend unavailable"
    except json.JSONDecodeError:
        # Invalid JSON response
        return "Backend unavailable"
    except Exception:
        # Any other unexpected error
        return "Backend unavailable"