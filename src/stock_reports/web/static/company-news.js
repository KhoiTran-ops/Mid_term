async function refreshCompanyNews() {
  const section = document.querySelector('#company-live-news');
  if (!section || document.hidden) return;
  try {
    const response = await fetch('/api/companies/' + encodeURIComponent(section.dataset.symbol) + '/news', {cache:'no-store'});
    if (!response.ok) throw new Error('news');
    const data = await response.json();
    const fragment = document.createDocumentFragment();
    for (const item of data.items) {
      if (!/^https?:\/\//.test(item.url)) continue;
      const article = document.createElement('article'); article.className='news-item';
      const title = document.createElement('h3'); const link=document.createElement('a');
      link.href=item.url; link.target='_blank'; link.rel='noopener noreferrer'; link.textContent=item.title;
      title.append(link); article.append(title);
      const meta=document.createElement('p'); meta.className='metadata';
      meta.textContent=(item.source_name || 'Nguồn tin') + ' · ' + (item.published_at ? new Date(item.published_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}) : 'Chưa rõ ngày đăng');
      article.append(meta); fragment.append(article);
    }
    section.querySelector('.company-news-items').replaceChildren(fragment);
    section.querySelector('.company-news-status').textContent=data.today_count ? data.today_count + ' tin liên quan trong ngày của ' + data.symbol : data.items.length ? 'Chưa ghi nhận tin đăng hôm nay; dưới đây là các tin liên quan gần nhất.' : 'Chưa có tin liên quan được nguồn cung cấp; không thay bằng tin doanh nghiệp khác.';
    const reportsResponse = await fetch('/api/reports?kind=stock&symbol=' + encodeURIComponent(data.symbol) + '&page_size=1', {cache:'no-store'});
    if (reportsResponse.ok) {
      const reports = await reportsResponse.json(); const latest=reports.items?.[0];
      let notice=section.querySelector('.latest-report-notice');
      if (latest && latest.id !== section.dataset.reportId) {
        if (!notice) { notice=document.createElement('p'); notice.className='latest-report-notice'; section.append(notice); }
        const link=document.createElement('a'); link.href='/reports/' + encodeURIComponent(latest.id);
        link.textContent='Đã có bản báo cáo cập nhật — mở bản mới'; notice.replaceChildren(link);
      } else if (notice) notice.remove();
    }
  } catch { section.querySelector('.company-news-status').textContent='Chưa lấy được tin mới; giữ danh sách đã tải.'; }
}
refreshCompanyNews();
setInterval(refreshCompanyNews,30000);
