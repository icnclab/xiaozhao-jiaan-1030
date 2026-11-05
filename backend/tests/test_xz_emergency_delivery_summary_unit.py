import unittest
from app.services.jiaan_emergency_delivery_summary import summarize_delivery_rows


class TestEmergencyDeliverySummary(unittest.TestCase):
    def test_empty(self):
        result = summarize_delivery_rows([])
        self.assertEqual(result['total_notification_jobs'], 0)
        self.assertFalse(result['has_notification_jobs'])
        self.assertFalse(result['delivery_confirmed'])

    def test_multiple_recipients(self):
        result = summarize_delivery_rows([
            {'stage':'new','status':'accepted','count':2},
            {'stage':'new','status':'failed','count':1},
            {'stage':'unacknowledged_60s','status':'skipped','count':3},
        ])
        self.assertEqual(result['total_notification_jobs'], 6)
        self.assertEqual(result['stages']['new']['accepted'], 2)
        self.assertEqual(result['stages']['unacknowledged_60s']['skipped'], 3)
        self.assertFalse(result['delivery_confirmed'])

    def test_unknown_status_is_ignored(self):
        result = summarize_delivery_rows([
            {'stage':'new','status':'unrecognized','count':4},
            {'stage':'bogus','status':'accepted','count':2},
        ])
        self.assertEqual(result['total_notification_jobs'], 0)

    def test_negative_count_rejected(self):
        with self.assertRaises(ValueError):
            summarize_delivery_rows([{'stage':'new','status':'accepted','count':-1}])

if __name__ == '__main__':
    unittest.main()
