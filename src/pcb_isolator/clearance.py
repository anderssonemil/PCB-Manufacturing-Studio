"""Measure available pin clearance against fixed cutting geometry."""
from math import hypot, floor


class ClearanceError(ValueError):
    def __init__(self,message,diagnostic):
        super().__init__(message);self.diagnostic=diagnostic


def measure_clearance(operations,alignment,pin_diameter,config):
    if config['alignment_pins'].get('pins_removed_before_machining'):return None
    best=None
    for name,moves,diameter in operations:
        machine=config['machine'];settings=config['alignment_pins']
        xy=(machine['origin_x_mm']+settings['start_x_mm'],machine['origin_y_mm']+settings['start_y_mm'])
        envelope=max(diameter,settings['tool_envelope_diameter_mm'])
        for move in moves:
            target=(move.get('x',xy[0]),move.get('y',xy[1]))
            if move['g']==1:
                dx,dy=target[0]-xy[0],target[1]-xy[1];length=dx*dx+dy*dy
                for pin in alignment:
                    t=max(0,min(1,((pin.x-xy[0])*dx+(pin.y-xy[1])*dy)/length)) if length else 0
                    point=(xy[0]+t*dx,xy[1]+t*dy)
                    gap=hypot(point[0]-pin.x,point[1]-pin.y)-(pin_diameter+envelope)/2
                    if best is None or gap<best['available_gap_mm']:
                        best={'operation':name,'pin_id':pin.id,'pin_xy':[pin.x,pin.y],
                              'closest_xy':list(point),'available_gap_mm':gap,
                              'tool_diameter_mm':diameter,'tool_envelope_diameter_mm':envelope}
            xy=target
    if best:
        best['requested_margin_mm']=config['alignment_pins']['xy_margin_mm']
        # Leave room beyond the planner's 0.002 mm rounding allowance.
        best['maximum_margin_mm']=floor((best['available_gap_mm']-.003)*1000)/1000
    return best
