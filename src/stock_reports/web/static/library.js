const dialog = document.querySelector('#generator');
const form = document.querySelector('#generate-form');
const status = document.querySelector('#generate-status');
const results = document.querySelector('#generate-results');
const submit = document.querySelector('#generate-submit');
const kind = document.querySelector('#generate-kind');
const dateInput = document.querySelector('#generate-date');
const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
const datePart = type => parts.find(p => p.type === type).value;
dateInput.value = [datePart('year'),datePart('month'),datePart('day')].join('-');
dateInput.max = dateInput.value;
document.querySelector('#open-generator').addEventListener('click', () => dialog.showModal());
document.querySelector('#close-generator').addEventListener('click', () => dialog.close());
function scope() {
  const stock = ['stock','all'].includes(kind.value);
  for (const [id, visible] of [['symbol',stock],['industry',kind.value==='industry'],['period',kind.value!=='macro'],['peers',kind.value!=='macro']]) {
    const wrapper = document.querySelector('#'+id+'-field');
    wrapper.hidden = !visible;
    const input = wrapper.querySelector('input,select');
    input.disabled = !visible;
    input.required = visible && ['symbol','industry'].includes(id);
  }
}
kind.addEventListener('change', scope);
scope();
form.addEventListener('submit', async event => {
  event.preventDefault();
  submit.disabled = true;
  results.replaceChildren();
  status.textContent = 'Đang phân tích dữ liệu và dựng PDF…';
  try {
    const body = Object.fromEntries(new FormData(form));
    if (body.symbol) body.symbol = body.symbol.trim().toUpperCase();
    if (!body.period) delete body.period;
    if (body.peers) body.peers = body.peers.split(/[ ,;]+/).filter(Boolean).map(s => s.toUpperCase());
    else delete body.peers;
    let response = await fetch('/api/report-jobs', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    let job = await response.json();
    if (!response.ok) throw new Error(job.error?.message || 'Không thể bắt đầu tạo báo cáo.');
    for (let attempt=0; attempt<180 && !['completed','failed'].includes(job.status); attempt++) {
      await new Promise(resolve => setTimeout(resolve,1000));
      response = await fetch('/api/report-jobs/'+job.id);
      if (!response.ok) throw new Error('Không thể đọc trạng thái báo cáo.');
      job = await response.json();
    }
    if (job.status==='failed') throw new Error(job.error);
    if (job.status!=='completed') throw new Error('Tác vụ vẫn chạy. Báo cáo hoàn tất sẽ xuất hiện trong thư viện.');
    status.textContent = 'Đã hoàn tất '+job.results.length+' báo cáo.';
    for (const item of job.results) {
      const link = document.createElement('a');
      link.href = '/reports/'+item.report.id;
      link.textContent = item.report.title;
      results.append(link);
    }
    const refresh = document.createElement('a');
    refresh.href = '/'; refresh.textContent = 'Cập nhật thư viện →';
    results.append(refresh);
  } catch (error) { status.textContent = error.message; }
  finally { submit.disabled = false; }
});
