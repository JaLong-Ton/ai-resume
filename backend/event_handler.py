"""FC event handler - returns the event it receives."""
import json

def handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "ok", "event_keys": list(event.keys()) if event else []})
    }
