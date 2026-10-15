"""Model checks: optimality, geometry, scheduling, reproducibility and export."""
from dataclasses import replace
import heapq
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from engine import (Config, astar, build_design, create_grid, create_scene, drone_at_time,
                    evaluate_design, generate_orders, is_blocked, nearest_node, risk_at,
                    segment_clear, simulate, xy)
from reporting import export_result, summary_rows


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design=build_design()
        cls.result=evaluate_design(cls.design)

    def test_repeatable_independent_evaluation(self):
        result=self.result
        self.assertNotEqual(result["design_seed"],result["evaluation_seed"])
        self.assertEqual(result["plans"],evaluate_design(self.design)["plans"])
        orders=result["plans"]["fixed"]["orders"]
        for plan in result["plans"].values():
            self.assertEqual(orders,plan["orders"])
        self.assertNotEqual(orders,generate_orders(result["scene"],Config(),result["design_seed"]))

    def test_layouts_frozen_across_evaluation_seeds(self):
        other=evaluate_design(self.design,20261016)
        for key in self.result["plans"]:
            self.assertEqual(self.result["plans"][key]["pad_ids"],other["plans"][key]["pad_ids"])
        with self.assertRaises(ValueError):
            evaluate_design(self.design,self.result["design_seed"])

    def test_layout_scores_are_minimal(self):
        candidates=self.result["candidates"]
        self.assertEqual(len(candidates),28)
        for key,score in (("combined","combined_score"),("distance","distance_score")):
            selected=next(c for c in candidates if c["pad_ids"]==self.result["plans"][key]["pad_ids"])
            self.assertAlmostEqual(selected[score],min(c[score] for c in candidates))

    def test_endpoints_and_clear_segments(self):
        for scenario in ("normal","closure"):
            design=self.design if scenario=="normal" else build_design(Config(scenario=scenario,altitude=25))
            scene=design["scene"]
            for key,route in design["routes"].items():
                if route is None:
                    continue
                pad_id,dest_id=key.split(":")
                pad=next(p for p in scene["pads"] if p["id"]==pad_id)
                dest=next(d for d in scene["deliveries"] if d["id"]==dest_id)
                self.assertEqual(route["points"][0],xy(pad))
                self.assertEqual(route["points"][-1],xy(dest))
                self.assertTrue(all(segment_clear(scene,a,b) for a,b in zip(route["points"],route["points"][1:])))
                self.assertAlmostEqual(route["distance"],route["cumulative"][-1])

    def test_risk_weight_tradeoff(self):
        scene=self.design["scene"]
        pad=next(p for p in scene["pads"] if p["id"]=="S3")
        dest=next(d for d in scene["deliveries"] if d["id"]=="D7")
        shortest=astar(scene,xy(pad),xy(dest),0)
        safer=astar(scene,xy(pad),xy(dest),5)
        self.assertLessEqual(safer["exposure"],shortest["exposure"]+1e-7)
        self.assertGreaterEqual(safer["distance"],shortest["distance"]-1e-7)

    def test_astar_cost_matches_dijkstra_on_small_graph(self):
        # Dijkstra has no heuristic. Check the target objective independently.
        scene=create_scene(Config(altitude=80))
        scene.update(width=96,height=96,step=16,clearance=0,buildings=[],
                     closure={"x":40,"y":0,"w":8,"h":65},
                     risk_zones=[{"x":64,"y":64,"rx":30,"ry":35,"weight":.8}])
        start,goal=(0,0),(96,96)
        grid=create_grid(scene)
        cols=grid["cols"]
        source,target=nearest_node(scene,grid,start),nearest_node(scene,grid,goal)
        distances={source:0.}
        heap=[(0.,source)]
        while heap:
            cost,u=heapq.heappop(heap)
            if cost>distances[u]:
                continue
            if u==target:
                break
            ux,uy=u%cols,u//cols
            # Build adjacency from pairs of neighbouring graph nodes.
            for v in range(cols*grid["rows"]):
                vx,vy=v%cols,v//cols
                dx,dy=abs(vx-ux),abs(vy-uy)
                if max(dx,dy)!=1 or grid["blocked"][v]:
                    continue
                if dx and dy and (grid["blocked"][uy*cols+vx] or grid["blocked"][vy*cols+ux]):
                    continue
                a,b=(ux*16,uy*16),(vx*16,vy*16)
                if not segment_clear(scene,a,b):
                    continue
                candidate=cost+math.dist(a,b)*(1+2*risk_at(scene,((a[0]+b[0])/2,(a[1]+b[1])/2)))
                if candidate<distances.get(v,math.inf):
                    distances[v]=candidate
                    heapq.heappush(heap,(candidate,v))
        route=astar(scene,start,goal,2,grid)
        self.assertIsNotNone(route)
        self.assertAlmostEqual(route["distance"]+2*route["exposure"],distances[target],places=7)

    def test_height_and_failure_accounting(self):
        low,high=create_scene(Config(altitude=25)),create_scene(Config(altitude=80))
        self.assertTrue(is_blocked(low,(650,100)))
        self.assertFalse(is_blocked(high,(650,100)))
        high["closure"]={"x":460,"y":0,"w":20,"h":high["height"]}
        self.assertIsNone(astar(high,(78,110),(900,350)))
        result=simulate(high,Config(altitude=80),["S1","S8"],[{"id":"O001","destination_id":"D6","created_at":0,"due_at":600}])
        self.assertEqual(result["stats"]["failed_orders"],1)
        self.assertEqual(result["stats"]["on_time_rate"],0)
        self.assertEqual(result["stats"]["completion_rate"],0)
        self.assertIsNone(result["stats"]["mean_delivery"])
        self.assertEqual(len(result["failed"]),1)

    def test_peak_demand_and_resource_nonoverlap(self):
        config=Config(scenario="peak",order_count=60)
        orders=generate_orders(self.design["scene"],config)
        self.assertEqual(len(orders),120)
        self.assertTrue(all(o["created_at"]<800 for o in orders))
        for pads in self.design["choices"].values():
            plan=simulate(self.design["scene"],config,pads,orders,self.design["routes"])
            for drone in plan["drones"]:
                jobs=sorted((j for j in plan["jobs"] if j["drone_id"]==drone["id"]),key=lambda j:j["prep_start"])
                self.assertTrue(all(b["prep_start"]>=a["end"]-1e-7 for a,b in zip(jobs,jobs[1:])))
            for calendar in plan["calendars"].values():
                self.assertTrue(all(b["start"]>=a["end"]-1e-7 for a,b in zip(calendar,calendar[1:])))
            for job in plan["jobs"]:
                times=[job[k] for k in ("created_at","prep_start","depart","arrived_dest","delivered_at","return_arrival","land_start","end")]
                self.assertEqual(times,sorted(times))
                self.assertGreaterEqual(job["pad_waiting"],-1e-7)

    def test_playback_matches_delivery_events(self):
        job=self.result["plans"]["combined"]["jobs"][0]
        scene=self.result["scene"]
        pad=next(p for p in scene["pads"] if p["id"]==job["pad_id"])
        dest=next(d for d in scene["deliveries"] if d["id"]==job["destination_id"])
        for time,point in ((job["depart"],pad),(job["arrived_dest"],dest),(job["return_arrival"],pad)):
            state=drone_at_time(self.result,"combined",job["drone_id"],time)
            self.assertLess(math.dist(xy(state),xy(point)),1e-6)

    def test_export_roundtrip_and_svg(self):
        with tempfile.TemporaryDirectory() as folder:
            export_result(self.result,folder)
            data=json.loads((Path(folder)/"result.json").read_text(encoding="utf-8"))
            self.assertEqual(data["plans"]["combined"]["stats"],self.result["plans"]["combined"]["stats"])
            for name in ("map.svg","comparison.svg"):
                self.assertEqual(ET.parse(Path(folder)/name).getroot().tag,"{http://www.w3.org/2000/svg}svg")
            self.assertTrue((Path(folder)/"failed.csv").exists())

    def test_batch_summary_records_missing_values(self):
        raw=[{"scenario":"normal","plan":"fixed","pads":"S1+S5",**{m:None for m in ("mean_delivery","mean_exposure","total_distance","mean_pad_waiting","on_time_rate","completion_rate","failed_orders")}}]
        raw.append({**raw[0],"mean_delivery":100})
        summary=summary_rows(raw)[0]
        self.assertEqual(summary["mean_delivery_valid_runs"],1)
        self.assertEqual(summary["mean_delivery_mean"],100)
        self.assertIsNone(summary["mean_exposure_mean"])

    def test_invalid_parameters(self):
        for change in ({"order_count":-2},{"order_count":True},{"order_count":2.5},{"speed":0},{"altitude":math.nan},{"risk_weight":-1},{"scenario":"unknown"},{"seed":-1}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                replace(Config(),**change).validated()


if __name__=="__main__":
    unittest.main()
