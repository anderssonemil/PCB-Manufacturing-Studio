"""Explicit manufacturing drill assignments; source geometry stays unchanged."""
from dataclasses import replace
from math import isfinite


def assignments(config):
    result={}
    for row in config['drilling'].get('assignments',[]):
        source=row.get('source_diameter_mm');tool=row.get('tool_diameter_mm')
        if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not isfinite(v) or v<=0 or v>100 for v in (source,tool)):
            raise ValueError('Drill diameters must be positive finite numbers, at most 100 mm.')
        key=round(source,6)
        if key in result:raise ValueError('Duplicate source drill size assignment.')
        if tool<.001:raise ValueError('Assigned drill diameter must be at least 0.001 mm.')
        result[key]=round(tool,6)
    return result


def group_drills(features,config):
    mapping=assignments(config);groups={};sources={}
    for feature in features:
        diameter=mapping.get(round(feature.diameter_mm,6),feature.diameter_mm)
        groups.setdefault(diameter,[]).append(replace(feature,diameter_mm=diameter))
        sizes=sources.setdefault(diameter,{})
        sizes[feature.diameter_mm]=sizes.get(feature.diameter_mm,0)+1
    return groups,sources
