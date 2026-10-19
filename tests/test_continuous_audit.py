"""An independent evidence checker must retain the documented episode boundary."""
import unittest

from airspace import Segment, segment_violation
from cases.verify_continuous_model import check


class IndependentAuditTests(unittest.TestCase):
    def test_ground_air_handoff_has_no_positive_overlap(self):
        pairs = [(0., 10., (0., 0.), (0., 0.), 'U1', 'A'),
                 (10., 20., (0., 0.), (10., 0.), 'U2', 'B')]
        audit = check(pairs, 20.)
        self.assertEqual(audit['overlapping_segment_pairs_checked'], 0)
        self.assertEqual(audit['zero_duration_interval_pairs_excluded'], 1)
        self.assertIsNone(segment_violation(Segment(0, 10, 0, 0, 0, 0),
                                            Segment(10, 20, 0, 0, 1, 0), 20))

    def test_positive_duration_contact_is_detected(self):
        pairs = [(0., 10., (0., 0.), (0., 0.), 'U1', 'A'),
                 (9.99, 20., (0., 0.), (10.01, 0.), 'U2', 'B')]
        with self.assertRaisesRegex(AssertionError, 'sustained separation violation'):
            check(pairs, 20.)
        self.assertIsNotNone(segment_violation(Segment(0, 10, 0, 0, 0, 0),
                                               Segment(9.99, 20, 0, 0, 1, 0), 20))

    def test_positive_overlap_at_threshold_is_permitted(self):
        audit = check([(0., 10., (0., 0.), (10., 0.), 'U1', 'A'),
                       (0., 10., (0., 20.), (10., 20.), 'U2', 'B')], 20.)
        self.assertEqual(audit['minimum_distance_m_on_positive_overlaps'], 20.)


if __name__ == '__main__':
    unittest.main()
