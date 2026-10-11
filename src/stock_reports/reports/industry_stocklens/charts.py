"""Offline SVG, signed scales and explicitly labelled actual/estimated/forecast."""
from html import escape
import math

COLORS=['#1F5EFF','#0E8F5A','#E8883A','#7B5AC1','#F2B01E','#587E9F','#C9363E']

def number(value,places=2,signed=False):
    if value is None:return 'Chưa có'
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):raise ValueError('Industry numeric display requires finite numbers')
    result=f'{abs(value):,.{places}f}'.replace(',','~').replace('.',',').replace('~','.')
    if places:result=result.rstrip('0').rstrip(',')
    return ('-' if value<0 else '+' if signed and value>0 else '')+result

def color(value,polarity='neutral'):
    if value is None or value==0:return '#51657a'
    if value<0:return '#C9363E'
    return '#0E8F5A' if polarity=='higher_good' else '#C9363E' if polarity=='higher_bad' else '#1F5EFF'

def columns(points,*,polarity='neutral',width=630,height=155):
    if not points or not any(p.get('value') is not None for p in points):return ''
    values=[p['value'] for p in points if p.get('value') is not None]
    lo=min(0,min(values));hi=max(0,max(values));span=hi-lo or 1;hi+=span*.19
    if lo<0:lo-=span*.06
    left=44;right=width-10;top=18;bottom=height-33
    y=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
    step=(right-left)/len(points);bar=min(36,step*.64)
    output=[f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Biểu đồ cột"><defs><pattern id="forecast-hatch" width="5" height="5" patternUnits="userSpaceOnUse"><path d="M0 5L5 0" stroke="#fff" stroke-width="1"/></pattern></defs>']
    for v in dict.fromkeys((lo,0,hi)):
        output.append(f'<line x1="{left}" x2="{right}" y1="{y(v):.2f}" y2="{y(v):.2f}" stroke="#d5dde5"/><text x="{left-6}" y="{y(v)+3:.2f}" font-size="8" text-anchor="end" fill="#51657a">{number(v,1)}</text>')
    label_step=max(1,math.ceil(len(points)/10))
    for i,p in enumerate(points):
        x=left+step*(i+.5);v=p.get('value');label=str(p.get('label',''))
        status=p.get('status');label=label if label.endswith(('A','E','F')) else label+(status or '')
        if v is not None:
            c=color(v,p.get('polarity',polarity));yy=min(y(v),y(0));h=abs(y(v)-y(0))
            output.append(f'<rect x="{x-bar/2:.2f}" y="{yy:.2f}" width="{bar:.2f}" height="{max(.5,h):.2f}" fill="{c}" opacity="{.45 if status=="F" else 1}"/>')
            if status=='F':output.append(f'<rect x="{x-bar/2:.2f}" y="{yy:.2f}" width="{bar:.2f}" height="{max(.5,h):.2f}" fill="url(#forecast-hatch)"/>')
            if len(points)<=14:output.append(f'<text x="{x:.2f}" y="{y(v)-5 if v>=0 else y(v)+12:.2f}" text-anchor="middle" font-size="8" fill="{c}">{number(v,1)}</text>')
        elif len(points)<=14:output.append(f'<text x="{x:.2f}" y="{y(0)-8:.2f}" text-anchor="middle" font-size="7" fill="#51657a">Chưa có</text>')
        if i%label_step==0 or i==len(points)-1:output.append(f'<text x="{x:.2f}" y="{height-8}" text-anchor="middle" font-size="8" fill="#51657a">{escape(label)}</text>')
    return ''.join(output)+'</svg>'

def stacked(rows):
    if not rows or any(r.get('pct') is None for r in rows) or abs(sum(r['pct'] for r in rows)-100)>.5 or any(r['pct']<0 or r['pct']>100 for r in rows):return ''
    parts=['<div class="share-track">'];legend=[]
    for i,r in enumerate(rows):
        c=COLORS[i%len(COLORS)];n=number(r['pct'],1);label=escape(str(r['name']))+('†' if r.get('derived') else '')
        parts.append(f'<span style="flex:{r["pct"]};background:{c}" title="{label}: {n}%"></span>')
        legend.append(f'<span><i style="background:{c}"></i>{label} <b class="mono">{n}%</b></span>')
    return ''.join(parts)+'</div><div class="share-legend">'+''.join(legend)+'</div>'

def horizontal(rows,key='value',*,polarity='neutral'):
    if not rows or not any(r.get(key) is not None for r in rows):return ''
    vals=[r[key] for r in rows if r.get(key) is not None];lo=min(0,min(vals));hi=max(0,max(vals));span=hi-lo or 1;zero=-lo/span*100
    result=[]
    for r in rows:
        label=escape(str(r.get('label',r.get('region',r.get('name','')))))
        width=abs(r[key])/span*100 if r.get(key) is not None else 0
        start=zero-width if r.get(key) is not None and r[key]<0 else zero
        result.append(f'<div class="bar-row"><span>{label}</span><div class="bar-track" style="position:relative"><b style="position:absolute;left:{zero}%;top:0;height:100%;border-left:1px solid #51657a"></b><i style="position:absolute;left:{start}%;width:{width}%;background:{color(r.get(key),polarity)}"></i></div><b class="mono">{number(r.get(key),1)}</b></div>')
    return ''.join(result)
