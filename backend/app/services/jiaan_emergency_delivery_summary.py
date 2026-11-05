"""Pure aggregation of emergency notification job states, no database access."""
from __future__ import annotations

STAGES = ('new', 'unacknowledged_60s', 'unacknowledged_180s')
STATUSES = ('queued', 'sending', 'accepted', 'failed', 'skipped')


def summarize_delivery_rows(rows) -> dict:
    """Report LINE platform request state, NOT actual handset delivery."""
    stages = {stage: {status: 0 for status in STATUSES} for stage in STAGES}
    total = 0
    for row in rows:
        stage = row['stage']
        status = row['status']
        if stage not in stages or status not in STATUSES:
            continue
        count = int(row['count'])
        if count < 0:
            raise ValueError('negative notification count')
        stages[stage][status] += count
        total += count
    return {
        'has_notification_jobs': total > 0,
        'total_notification_jobs': total,
        'stages': stages,
        'delivery_confirmed': False,
    }
