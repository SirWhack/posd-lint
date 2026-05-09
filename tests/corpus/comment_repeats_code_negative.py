"""Should NOT flag: comments that add information beyond the code."""


def schedule_reminder(user_id, interval):
    # Use UTC to avoid DST gaps when reminders cross midnight in user's tz
    reminder_time = compute_next_window(interval)
    # Mark as preliminary; the slot acquirer will confirm idempotently
    return claim_slot(user_id, reminder_time)


def compute_next_window(x):
    return x


def claim_slot(u, t):
    return True


# TODO: revisit retry policy after we add idempotency keys
def post_payload(p):
    return p
