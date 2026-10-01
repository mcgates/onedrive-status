import unittest
from status import parse_logs, apply_service_state

class StatusTests(unittest.TestCase):
    now = 10000
    def rows(self, messages):
        return [{'MESSAGE': m, '__REALTIME_TIMESTAMP': str(int((self.now - 3 + i) * 1e6))} for i, m in enumerate(messages)]
    def completed(self):
        return parse_logs(self.rows(['Starting a sync with Microsoft OneDrive', 'Syncing changes from Microsoft OneDrive ...', 'Sync with Microsoft OneDrive is complete']), self.now)
    def test_completed_cycle(self):
        self.assertEqual(self.completed().color, '#22c55e')
        self.assertEqual(self.completed().last_sync, self.now - 1)
    def test_unavailable_service_does_not_override_logs(self):
        for state in ['', 'unknown', 'active']:
            self.assertEqual(apply_service_state(self.completed(), state).label, 'Last sync completed')
    def test_stopped_service(self):
        for state in ['inactive', 'failed', 'deactivating']:
            self.assertEqual(apply_service_state(self.completed(), state).color, '#ef4444')
    def test_syncing(self):
        self.assertEqual(parse_logs(self.rows(['Starting a sync with Microsoft OneDrive']), self.now).label, 'Syncing')
    def test_error(self):
        self.assertEqual(parse_logs(self.rows(['ERROR: connection failed']), self.now).label, 'Needs attention')
    def test_stale(self):
        self.assertEqual(parse_logs(self.rows(['Sync with Microsoft OneDrive is complete']), self.now + 1000).label, 'Status is stale')
    def test_empty(self):
        self.assertEqual(parse_logs([], self.now).label, 'No recent status')

if __name__ == '__main__':
    unittest.main()
