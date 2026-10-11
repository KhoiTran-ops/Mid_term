"""Offline SVG charts with data-driven signed scales and escaped labels."""
from html import escape
import math

COLORS=['#1F5EFF','#E8883A','#0E8F5A']
def fmt(value,places=1):
    return f'{value:,.{places}f}'.replace(',','~').replace('.',',').replace('~','.')

def chart(rows,metrics,*,kind='bar',height=156,polarity='higher_good',gdp=False,width=650):
    if not rows or not any(isinstance(r.get(k),(int,float)) for _,k in metrics for r in rows):return None
    left=47;right=12;top=27;bottom=30
    values=[r[k] for _,k in metrics for r in rows if r.get(k) is not None]
    lo=min(0,min(values));hi=max(0,max(values));span=hi-lo or 1
    hi+=span*.18;lo-=span*.1 if lo<0 else 0
    y=lambda v:top+(hi-v)/(hi-lo)*(height-top-bottom)
    x=lambda i:left+(i+.5)*(width-left-right)/len(rows)
    parts=[f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Biểu đồ dữ liệu" xmlns="http://www.w3.org/2000/svg">']
    for j in range(4):
        v=lo+(hi-lo)*j/3;yy=y(v)
        parts.append(f'<line x1="{left}" x2="{width-right}" y1="{yy}" y2="{yy}" stroke="#e5eaf0"/><text x="{left-7}" y="{yy+3}" text-anchor="end" font-size="9" fill="#51657a">{fmt(v)}</text>')
    parts.append(f'<line x1="{left}" x2="{width-right}" y1="{y(0)}" y2="{y(0)}" stroke="#9aaabc"/>')
    step=(width-left-right)/len(rows)
    for series,(name,key) in enumerate(metrics):
        for i,row in enumerate(rows):
            v=row.get(key)
            if v is None:continue
            color=COLORS[series%len(COLORS)]
            if len(metrics)==1:
                color='#51657a' if polarity=='neutral' else '#0E8F5A' if (v>=0)==(polarity=='higher_good') else '#C9363E'
            if gdp:color='#C9363E' if v<3 else '#1F5EFF'
            if kind=='line':
                if i and rows[i-1].get(key) is not None:
                    prev=rows[i-1][key];segment='#C9363E' if gdp and min(prev,v)<3 else color
                    parts.append(f'<line x1="{x(i-1)}" y1="{y(prev)}" x2="{x(i)}" y2="{y(v)}" stroke="{segment}" stroke-width="2.5"/>')
                parts.append(f'<circle cx="{x(i)}" cy="{y(v)}" r="3" fill="{color}"/>');xx=x(i)
            else:
                w=min(40,step*.68/len(metrics));xx=x(i)+(series-(len(metrics)-1)/2)*w
                parts.append(f'<rect x="{xx-w*.43}" y="{min(y(v),y(0))}" width="{w*.86}" height="{max(1,abs(y(v)-y(0)))}" rx="2" fill="{color}"/>')
            # Stagger the first series away from the bars to avoid merged labels
            # when paired values are close; both positive labels remain above bars.
            extra=9 if len(metrics)>1 and series==0 else 0
            label_y=y(v)-7-extra if v>=0 else y(v)+12+extra
            parts.append(f'<text x="{xx}" y="{label_y}" text-anchor="middle" font-size="{8 if len(rows)>10 or len(metrics)>1 else 10}" fill="#0B1F33">{fmt(v)}</text>')
    for i,row in enumerate(rows):
        label=str(row.get('year',row.get('month',row.get('quarter',row.get('date','')))))
        parts.append(f'<text x="{x(i)}" y="{height-8}" text-anchor="middle" font-size="9" fill="#51657a">{escape(label)}</text>')
    parts.append('</svg>')
    legend=' · '.join(f'<span style="color:{COLORS[i%len(COLORS)]}">● {escape(name)}</span>' for i,(name,_) in enumerate(metrics)) if len(metrics)>1 else ''
    return ''.join(parts)+f'<div class="legend">{legend}</div>'

def pmi_scale(value):
    if value is None:return None
    low=min(45,value-2);high=max(55,value+2)
    at=lambda x:40+(x-low)/(high-low)*570
    return f'<svg viewBox="0 0 650 86" role="img" aria-label="PMI và ngưỡng 50"><rect x="40" y="30" width="570" height="15" rx="7" fill="#dfe8f4"/><rect x="{at(50)}" y="30" width="{610-at(50)}" height="15" fill="#d6eee5"/><line x1="{at(50)}" x2="{at(50)}" y1="20" y2="55" stroke="#0B1F33" stroke-width="2"/><circle cx="{at(value)}" cy="37" r="7" fill="#1F5EFF"/><text x="{at(value)}" y="15" text-anchor="middle" font-size="13">{fmt(value)}</text><text x="40" y="72" font-size="11">{fmt(low,0)}</text><text x="{at(50)}" y="72" text-anchor="middle" font-size="11">50 · ngưỡng mở rộng</text><text x="610" y="72" text-anchor="end" font-size="11">{fmt(high,0)}</text></svg>'
