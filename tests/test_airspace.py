from dataclasses import replace
import math
import unittest

from airspace import Segment, detect_conflicts, flight_segments, segment_violation
from engine import Config, create_scene, measure_path, simulate


class AirspaceTests(unittest.TestCase):
    def setUp(self):
        self.scene=create_scene(Config(altitude=80))
        self.scene.update(width=100,height=100,buildings=[],risk_zones=[],closure=None,
                          pads=[{"id":"S1","x":0,"y":50},{"id":"S2","x":100,"y":50}])
        self.routes={"S1:D1":measure_path(self.scene,[(0,50),(50,50),(100,50)]),
                     "S2:D2":measure_path(self.scene,[(100,50),(50,50),(0,50)]),
                     "S1:D2":None,"S2:D1":None}
        self.orders=[{"id":"O001","destination_id":"D1","created_at":0,"due_at":600},
                     {"id":"O002","destination_id":"D2","created_at":0,"due_at":600}]
        self.config=Config(drone_count=2,speed=10,separation=10)

    def test_subsecond_crossing_detected_analytically(self):
        a=Segment(0,1,-100,0,200,0)
        b=Segment(0,1,0,-100,0,200)
        event=segment_violation(a,b,1)
        self.assertAlmostEqual(event["closest_time"],.5)
        self.assertAlmostEqual(event["min_distance"],0.)
        half_width=1/math.sqrt(200**2+200**2)
        self.assertAlmostEqual(event["start"],.5-half_width)
        self.assertAlmostEqual(event["end"],.5+half_width)
        self.assertLess(event["end"]-event["start"],.01)

    def test_parallel_tangent_and_nonoverlapping_times(self):
        a=Segment(0,10,0,0,1,0)
        self.assertIsNone(segment_violation(a,Segment(0,10,0,20,1,0),20))
        close=segment_violation(a,Segment(0,10,0,19,1,0),20)
        self.assertEqual((close["start"],close["end"]),(0,10))
        self.assertAlmostEqual(close["min_distance"],19)
        self.assertIsNone(segment_violation(a,Segment(10,20,10,0,1,0),20))

    def test_hover_phase_is_checked(self):
        moving=Segment(0,10,-50,0,10,0)
        hover=Segment(2,8,0,0,0,0)
        event=segment_violation(moving,hover,10)
        self.assertAlmostEqual(event["start"],4)
        self.assertAlmostEqual(event["end"],6)
        self.assertAlmostEqual(event["closest_time"],5)

    def test_episode_merges_across_route_knots(self):
        baseline=simulate(self.scene,replace(self.config,deconflict=False),["S1","S2"],self.orders,self.routes)
        events=baseline["conflicts"]
        self.assertEqual(len(events),2)  # one outbound and one return encounter
        self.assertTrue(all(e["min_distance"]<1e-8 for e in events))
        self.assertTrue(all(abs((e["end"]-e["start"])-1)<1e-7 for e in events))

    def test_staggered_departures_remove_conflicts_without_dropping_jobs(self):
        baseline=simulate(self.scene,replace(self.config,deconflict=False),["S1","S2"],self.orders,self.routes)
        improved=simulate(self.scene,self.config,["S1","S2"],self.orders,self.routes)
        self.assertGreater(baseline["stats"]["air_conflict_count"],0)
        self.assertEqual(improved["stats"]["delivered_orders"],2)
        self.assertEqual(improved["stats"]["air_conflict_count"],0)
        self.assertGreater(improved["stats"]["mean_airspace_delay"],0)
        self.assertEqual(detect_conflicts(improved["jobs"],self.routes,10,10),[])
        for job in improved["jobs"]:
            self.assertAlmostEqual(job["prep_start"]-job["ready"]+job["land_start"]-job["return_arrival"],
                                   job["pad_waiting"]+job["airspace_delay"])

    def test_search_limit_failure_is_explicit_and_counted(self):
        config=replace(self.config,max_airspace_delay=0)
        plan=simulate(self.scene,config,["S1","S2"],self.orders,self.routes)
        self.assertEqual(plan["stats"]["airspace_failed_orders"],1)
        self.assertEqual(plan["stats"]["unreachable_orders"],0)
        self.assertEqual(plan["stats"]["completion_rate"],.5)
        self.assertEqual(plan["stats"]["on_time_rate"],.5)
        self.assertEqual(plan["failed"][0]["failure_type"],"airspace_delay_limit")

    def test_landing_hold_and_ground_exclusion(self):
        plan=simulate(self.scene,replace(self.config,deconflict=False),["S1","S2"],self.orders[:1],self.routes)
        job=dict(plan["jobs"][0])
        job["land_start"]=job["return_arrival"]+15
        job["end"]=job["land_start"]+20
        segments=flight_segments(job,self.routes[job["route_key"]],10)
        self.assertEqual(segments[0].start,job["depart"])
        self.assertEqual(segments[-1].start,job["return_arrival"])
        self.assertEqual(segments[-1].end,job["land_start"])
        self.assertEqual(segments[-1].position(job["land_start"]),(0.,50.))

    def test_invalid_safety_parameters(self):
        for change in ({"deconflict":1},{"separation":0},{"separation":math.inf},
                       {"departure_step":0},{"max_airspace_delay":-1},{"departure_step":1e-8}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                replace(self.config,**change).validated()


if __name__=="__main__":
    unittest.main()
