// Refresh the saved news list without replacing filters the reader is editing.
async function refreshNews() {
  if (document.hidden || document.querySelector('#news-results').contains(document.activeElement)) return;
  try {
    const response = await fetch(window.location.href, { cache: 'no-store' });
    if (!response.ok) throw new Error('Refresh failed');
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    for (const selector of ['#news-results', '.news-status']) {
      const current = document.querySelector(selector);
      const next = page.querySelector(selector);
      if (current && next) current.replaceWith(next);
    }
    const oldIssues = document.querySelector('.source-issues');
    const newIssues = page.querySelector('.source-issues');
    if (oldIssues) oldIssues.remove();
    if (newIssues) document.querySelector('.news-status').after(newIssues);
  } catch {
    document.querySelector('#refresh-message').textContent = 'Chưa làm mới được danh sách. Đang giữ các tin đã tải.';
  }
}
setInterval(refreshNews, 60000);
