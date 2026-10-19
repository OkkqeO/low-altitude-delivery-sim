"""Independent closest-approach check for exported ideal flight trajectories.

This does not import the production airspace detector. Airborne intervals exclude
takeoff preparation and landing service. A zero-duration shared endpoint is not
a sustained separation episode, matching the documented model, not real flight.
"""
import math


def reconstruct(job, points, speed):
    segments = []
    for route, begin, expected in ((points, job['depart'], job['arrived_dest']),
                                    (list(reversed(points)), job['return_start'], job['return_arrival'])):
        now = begin
        for a, b in zip(route, route[1:]):
            end = now + math.dist(a, b)/speed
            if end > now:
                segments.append((now, end, tuple(a), tuple(b), job['drone_id'], job['order_id']))
            now = end
        assert math.isclose(now, expected, rel_tol=1e-10, abs_tol=1e-7)
    for begin, end, point in ((job['arrived_dest'], job['return_start'], points[-1]),
                              (job['return_arrival'], job['land_start'], points[0])):
        if end > begin:
            segments.append((begin, end, tuple(point), tuple(point), job['drone_id'], job['order_id']))
    return segments


def check(segments, threshold):
    active, pairs, zero_time_contacts, minimum = [], 0, 0, math.inf
    for s in sorted(segments):
        active = [t for t in active if t[1] >= s[0]-1e-9]
        for t in active:
            if s[4] == t[4]:
                continue
            begin, end = max(s[0], t[0]), min(s[1], t[1])
            if end-begin <= 1e-9:
                if abs(end-begin) <= 1e-9:
                    zero_time_contacts += 1
                continue
            positions, velocities = [], []
            for piece in (s, t):
                v = tuple((piece[3][i]-piece[2][i])/(piece[1]-piece[0]) for i in (0, 1))
                positions.append(tuple(piece[2][i]+v[i]*(begin-piece[0]) for i in (0, 1)))
                velocities.append(v)
            r = tuple(positions[0][i]-positions[1][i] for i in (0, 1))
            v = tuple(velocities[0][i]-velocities[1][i] for i in (0, 1))
            vv = sum(x*x for x in v)
            dt = min(end-begin, max(0., -sum(r[i]*v[i] for i in (0, 1))/vv)) if vv else 0.
            distance = math.hypot(*(r[i]+dt*v[i] for i in (0, 1)))
            minimum = min(minimum, distance)
            assert distance >= threshold-1e-6, ('sustained separation violation', s, t, distance)
            pairs += 1
        active.append(s)
    return {'overlapping_segment_pairs_checked': pairs,
            'zero_duration_interval_pairs_excluded': zero_time_contacts,
            'minimum_distance_m_on_positive_overlaps': minimum if math.isfinite(minimum) else None}


def audit_result(result):
    jobs, segments, pairs, excluded, minimum = 0, 0, 0, 0, math.inf
    for plan in result['plans'].values():
        trajectory = []
        for job in plan['jobs']:
            trajectory.extend(reconstruct(job, result['routes'][job['route_key']]['points'], result['config']['speed']))
        values = check(trajectory, result['config']['separation'])
        pairs += values['overlapping_segment_pairs_checked']
        excluded += values['zero_duration_interval_pairs_excluded']
        if values['minimum_distance_m_on_positive_overlaps'] is not None:
            minimum = min(minimum, values['minimum_distance_m_on_positive_overlaps'])
        for calendar in plan['calendars'].values():
            assert all(a['end'] <= b['start']+1e-8 for a, b in zip(calendar, calendar[1:]))
        for drone in plan['drones']:
            tasks = sorted((j for j in plan['jobs'] if j['drone_id'] == drone['id']), key=lambda j: j['prep_start'])
            assert all(a['end'] <= b['prep_start']+1e-8 for a, b in zip(tasks, tasks[1:]))
        jobs += len(plan['jobs'])
        segments += len(trajectory)
    return {'task_records': jobs, 'trajectory_segments': segments,
            'overlapping_segment_pairs_checked': pairs,
            'zero_duration_interval_pairs_excluded': excluded,
            'minimum_distance_m_on_positive_overlaps': minimum if math.isfinite(minimum) else None,
            'continuous_episode_violations': 0, 'resource_overlaps': 0}
