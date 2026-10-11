"""Explainable daily relevance, not fabricated readership/popularity metrics."""
from datetime import date,datetime,time,timedelta
from zoneinfo import ZoneInfo
from stock_reports.data_sources.news.normalize import contains

VIETNAM=ZoneInfo('Asia/Ho_Chi_Minh')
PRIORITY=('báo cáo tài chính','kết quả kinh doanh','lợi nhuận','doanh thu','cổ tức','phát hành','mua lại','sáp nhập','hợp đồng','earnings','dividend','capital','merger')


def rank_company_news(rows,symbol,as_of,limit=12):
    day=date.fromisoformat(as_of) if isinstance(as_of,str) else as_of
    cutoff=datetime.combine(day,time.max,VIETNAM)
    selected=[]
    for row in rows:
        stamp=row.get('published_at'); published=datetime.fromisoformat(stamp).astimezone(VIETNAM) if stamp else None
        if published and published>cutoff:continue
        item=dict(row)
        title=row.get('title') or ''
        today=bool(published and published.date()==day)
        topic=sum(contains(title,word) for word in PRIORITY)
        headline=contains(title,symbol)
        recent=published.timestamp() if published else 0
        # Today first. Within today, direct issuer headlines/business catalysts;
        # otherwise use recency, never promote years-old items as today's news.
        key=(today,headline if today else False,topic if today else 0,recent)
        selected.append((key,item))
    selected.sort(key=lambda x:x[0],reverse=True)
    return [item for _,item in selected[:limit]]
