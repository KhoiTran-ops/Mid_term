"""Pure SVG geometry; no market/financial calculation in the template."""
from html import escape
import math
from markupsafe import Markup

COLORS=['#1F5EFF','#0E8F5A','#F2B01E','#8458B3']


def line_chart(labels,series,*,height=130,bands=(),percent_axis=False):
    width=650;left=55;right=630;top=12;bottom=height-27
    values=[v for _,data in series for v in data if v is not None and math.isfinite(v)]
    if not values:return None
    low=min([*values,*bands]);high=max([*values,*bands]);pad=(high-low)*.1 or max(abs(high)*.02,1);low-=pad;high+=pad
    if percent_axis:
        step=5 if high-low<=30 else 10 if high-low<=60 else 20
        low=math.floor(low/step)*step;high=math.ceil(high/step)*step
    y=lambda v:bottom-(v-low)/(high-low)*(bottom-top)
    x=lambda i:left+i/max(len(labels)-1,1)*(right-left)
    parts=[f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Biểu đồ dữ liệu thực">']
    ticks=[low+(high-low)*i/2 for i in range(3)] if not percent_axis else list(range(int(low),int(high)+1,step))
    for val in ticks:
        yy=y(val);label=f'{val:.0f}%' if percent_axis else f'{val:,.1f}'
        parts.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{right}" y2="{yy:.2f}" stroke="#e3e9ef"/><text x="48" y="{yy+3:.2f}" text-anchor="end">{label}</text>')
    for value in bands:
        if low<=value<=high:parts.append(f'<line x1="{left}" x2="{right}" y1="{y(value):.2f}" y2="{y(value):.2f}" stroke="#F2B01E" stroke-dasharray="4 3"/>')
    for j,(name,data) in enumerate(series):
        segments=[];segment=[]
        for i,value in enumerate(data):
            if value is None:
                if segment:segments.append(segment);segment=[]
            else:segment.append((x(i),y(value)))
        if segment:segments.append(segment)
        for segment in segments:
            if len(segment)==1:
                parts.append(f'<circle cx="{segment[0][0]:.2f}" cy="{segment[0][1]:.2f}" r="2" fill="{COLORS[j%4]}"/>')
            else:parts.append('<polyline points="'+' '.join(f'{a:.2f},{b:.2f}' for a,b in segment)+f'" fill="none" stroke="{COLORS[j%4]}" stroke-width="1.5"/>')
    for i in (range(len(labels)) if len(labels)<=5 else sorted({0,len(labels)//2,len(labels)-1})):
        if labels:parts.append(f'<text x="{x(i):.2f}" y="{height-7}" text-anchor="middle">{escape(str(labels[i]))}</text>')
    parts.append('</svg>');return Markup(''.join(parts))


def bar_chart(labels,series,*,height=145,stacked=False,semantic=False):
    width=650;left=45;right=635;top=18;bottom=height-29
    values=[v for _,data in series for v in data if v is not None]
    if not values:return None
    high=max(max(values),0);low=min(min(values),0)
    if stacked:
        high=max([sum(data[i] for _,data in series if data[i] is not None and data[i]>0) for i in range(len(labels))]+[high])
    high+=max((high-low)*.1,1e-6)
    if high==low:high=low+1
    y=lambda v:bottom-(v-low)/(high-low)*(bottom-top)
    slot=(right-left)/max(len(labels),1);bw=min(52,slot*.65/max(1,1 if stacked else len(series)))
    parts=[f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Biểu đồ dữ liệu thực">',f'<line x1="{left}" x2="{right}" y1="{y(0):.2f}" y2="{y(0):.2f}" stroke="#d5dde5"/>']
    for i,label in enumerate(labels):
        base=0
        for j,(name,data) in enumerate(series):
            value=data[i]
            if value is None:continue
            start=base if stacked else 0;end=start+value
            xx=left+i*slot+slot/2+(0 if stacked else (j-(len(series)-1)/2)*bw)-bw/2
            color='#C9363E' if value<0 else '#0E8F5A' if semantic and value>0 else COLORS[j%4]
            parts.append(f'<rect x="{xx:.2f}" y="{min(y(start),y(end)):.2f}" width="{bw-3:.2f}" height="{max(abs(y(end)-y(start)),.6):.2f}" fill="{color}"><title>{escape(str(label))}: {value:,.2f}</title></rect>')
            if not stacked:parts.append(f'<text x="{xx+bw/2:.2f}" y="{min(y(start),y(end))-4:.2f}" text-anchor="middle">{value:,.1f}</text>')
            if stacked:base=end
        parts.append(f'<text x="{left+i*slot+slot/2:.2f}" y="{height-7}" text-anchor="middle">{escape(str(label))}</text>')
    parts.append('</svg>');return Markup(''.join(parts))
