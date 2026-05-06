from datetime import datetime, timedelta, timezone

# Mumbai/India is UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

def get_now():
    """Return current datetime in Mumbai (IST) timezone."""
    return datetime.now(IST)

def get_now_naive():
    """Return current datetime in Mumbai (IST) timezone as a naive object for DB compatibility."""
    return datetime.now(IST).replace(tzinfo=None)
