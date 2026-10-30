"""Ordered XYZ motions for an offline animation of generated router programs."""
import math
import re


def parse_motions(text,start):
    position=[float(start[0]),float(start[1]),None]
    feed=None;motions=[]
    xy_first='XY FIRST STARTUP - TOOL SETTING MUST LEAVE Z AT MAX HEIGHT' in text
    for raw in text.splitlines():
        line=re.sub(r'\([^)]*\)','',raw).split(';',1)[0].strip()
        if not line or line=='%':continue
        words={key:float(value) for key,value in re.findall(r'([A-Z])([-+]?\d+(?:\.\d*)?)',line)}
        if 'S' in words:raise ValueError('Animation encountered an unexpected spindle-speed command.')
        if 'G' not in words:continue
        if words['G'] not in (0,1):raise ValueError('Animation supports the generated G00/G1 moves only.')
        if 'F' in words:feed=words['F']
        target=list(position)
        for index,axis in enumerate('XYZ'):
            if axis in words:target[index]=words[axis]
        if not any(axis in words for axis in 'XYZ'):continue
        unknown=position[2] is None
        if target[2] is None:
            if xy_first and not motions and words['G']==0:
                position=target
                continue  # Actual starting XY/Z are unknown; do not invent that motion.
            raise ValueError('Animation encountered XY motion before a commanded Z height.')
        initial=list(position);initial[2]=target[2] if unknown else initial[2]
        length=math.dist(initial,target)
        rapid=words['G']==0
        if not rapid and (feed is None or not math.isfinite(feed) or feed<=0):
            raise ValueError('Animation needs a positive feed for each cutting move.')
        motions.append({'from':initial,'to':target,'rapid':rapid,'feed':None if rapid else feed,
                        'length_mm':length,'initial_z_unknown':unknown})
        position=target
    return motions


def animation_assets():
    from pathlib import Path
    return Path(__file__).with_name('router_animation.js').read_text(encoding='utf-8')
