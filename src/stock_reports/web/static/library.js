const dialog = document.querySelector('#generator');
async function refreshDataStatus() {
  const node = document.querySelector('#financial-refresh-status');
  if (!node) return;
  try {
    const response = await fetch('/api/data-status');
    if (!response.ok) return;
    const data = await response.json();
    if (data.status === 'not_started') { node.textContent = ''; return; }
    const state = {running:'Đang cập nhật',completed:'Đã cập nhật',completed_with_gaps:'Đã cập nhật, nguồn còn thiếu',failed:'Cập nhật bị lỗi',interrupted:'Cập nhật tạm dừng',stale:'Chưa nhận tiến độ mới; cần kiểm tra tiến trình'};
    node.textContent = `${state[data.status] || data.status} BCTC năm 2021–2025 và lịch sử quý: ${data.completed ?? 0}/${data.total ?? 0} mã đã rà soát. `+
      `${data.annual_complete_companies ?? 0} mã có đủ 5 năm ở cả ba nhóm báo cáo; ${data.quarterly_complete_latest_eight ?? 0} mã có đủ ba nhóm ở 8 quý gần nhất. `+
      (data.current_symbol && data.status === 'running' ? `Đang tải: ${data.current_symbol}. ` : '')+
      'Có số liệu không đồng nghĩa toàn bộ thuyết minh đã được kiểm chứng.';
  } catch (_) { /* Keep the last truthful status if a refresh fails. */ }
}
refreshDataStatus();
setInterval(refreshDataStatus, 15000);
const form = document.querySelector('#generate-form');
const status = document.querySelector('#generate-status');
const results = document.querySelector('#generate-results');
const submit = document.querySelector('#generate-submit');
const kind = document.querySelector('#generate-kind');
const dateInput = document.querySelector('#generate-date');
const horizonField=document.createElement('div');
horizonField.className='field';horizonField.id='horizon-field';
horizonField.innerHTML='<label for="generate-horizon">Khung phân tích StockLens</label><select id="generate-horizon" name="horizon"><option value="short">Ngắn hạn</option><option value="medium" selected>Trung hạn</option><option value="long">Dài hạn</option></select>';
document.querySelector('#period-field').before(horizonField);
const macroPeriodField=document.createElement('div');
macroPeriodField.className='field';macroPeriodField.id='macro_period-field';
macroPeriodField.innerHTML='<label for="generate-macro-period">Kỳ vĩ mô (để trống: kỳ đã công bố mới nhất)</label><input id="generate-macro-period" name="macro_period" placeholder="2026-9T" pattern="[0-9]{4}(-9T|-Q[1-4]|-(0[1-9]|1[0-2]))?"><small>Tháng: 2026-09 · Quý: 2026-Q3 · Năm: 2026. Chỉ dùng dữ liệu đúng kỳ; không thay bằng số liệu năm.</small>';
document.querySelector('#period-field').after(macroPeriodField);
const industryPeriodField=document.createElement('div');
industryPeriodField.className='field';industryPeriodField.id='industry_period-field';
industryPeriodField.innerHTML='<label for="generate-industry-period">Kỳ báo cáo ngành (để trống: tháng hiện tại)</label><input id="generate-industry-period" name="industry_period" placeholder="2026-10" pattern="[0-9]{4}(-9T|-Q[1-4]|-(0[1-9]|1[0-2]))?"><small>Kỳ ngành độc lập kỳ BCTC; mỗi bảng ghi đúng năm/quý nguồn. Trang thiếu nhóm dữ liệu sẽ được ẩn.</small>';
macroPeriodField.after(industryPeriodField);
const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
const datePart = type => parts.find(p => p.type === type).value;
dateInput.value = [datePart('year'),datePart('month'),datePart('day')].join('-');
dateInput.max = dateInput.value;
document.querySelector('#open-generator').addEventListener('click', () => dialog.showModal());
document.querySelector('#close-generator').addEventListener('click', () => dialog.close());
function scope() {
  const stock = ['stock','all'].includes(kind.value);
  for (const [id, visible] of [['symbol',stock],['horizon',stock],['industry',kind.value==='industry'],['period',stock],['macro_period',['macro','all'].includes(kind.value)],['industry_period',['industry','all'].includes(kind.value)],['peers',stock]]) {
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
    if (!body.macro_period) delete body.macro_period;
    if (!body.industry_period) delete body.industry_period;
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
