"""Empirical motion estimate for the unchanged laser preset, not machine control."""
from math import ceil
import numpy as np
from .adaptive_isolation import line_parts


def estimate_laser_time(contours):
    routes=[p for shape in contours for p in line_parts(shape)]
    length=sum(p.length for p in routes)
    travel=0.0
    if routes:
        starts=np.asarray([p.coords[0] for p in routes]);ends=np.asarray([p.coords[-1] for p in routes])
        used=np.zeros(len(routes),dtype=bool);used[0]=True;position=ends[0]
        for _ in range(len(routes)-1):
            a=np.linalg.norm(starts-position,axis=1);b=np.linalg.norm(ends-position,axis=1)
            distances=np.minimum(a,b);distances[used]=np.inf
            i=int(np.argmin(distances));travel+=float(distances[i])
            position=ends[i] if a[i]<=b[i] else starts[i];used[i]=True
    # Connected-line trial: 790 mm / 93 s. Travel estimate from earlier
    # disconnected coupon; per-object residual checked against 45x30 coupon,
    # 997.99 mm, 292 objects, observed 125 seconds (2026-10-25).
    seconds=length/(790/93)+travel/82.51965556+len(routes)*.01589056218
    def label(value):
        value=ceil(value);return f'{value//60}:{value%60:02}'
    return {'estimated_seconds':seconds,'estimate':label(seconds),
        'range':label(seconds*.85)+' to '+label(seconds*1.15),
        'laser_on_length_mm':length,'estimated_travel_mm':travel,'objects':len(routes),
        'note':'Same speed/power preset as calibration. Estimated endpoint sorting; controller ordering, acceleration and paint variation can change runtime. Includes isolation routes; alignment marks add negligible travel.'}
