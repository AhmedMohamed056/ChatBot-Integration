from backend_client import send_message_to_backend
import sys
import io

# Ensure stdout can handle Unicode
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def handle_incoming_message(phone: str, message: str) -> str:
    """
    Entry point for incoming WhatsApp messages.
    Logs the incoming message, sends to backend via HTTP, and returns the reply.

    Args:
        phone: The phone number of the sender
        message: The message content

    Returns:
        str: The backend reply
    """
    print(f"Incoming message", file=sys.stderr)
    print(f"Phone: {phone}", file=sys.stderr)
    print(f"Message: {message}", file=sys.stderr)

    reply = send_message_to_backend(
        phone,
        message
    )

    print("Backend reply:", file=sys.stderr)
    print(reply, file=sys.stderr)

    return reply

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        phone = sys.argv[1]
        message = sys.argv[2]
        reply = handle_incoming_message(phone, message)
        print(reply)
    else:
        print("Usage: python whatsapp_handler.py <phone> <message>")
        sys.exit(1)
