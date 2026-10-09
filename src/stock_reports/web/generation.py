"""Bounded local jobs sharing the CLI report service."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from stock_reports.pipeline.research_reports import GenerationRequest, generate_reports, report_analysis


class ReportJobs:
    def __init__(self, settings):
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='research-pdf')
        self.lock = Lock()
        self.jobs = {}

    def submit(self, request):
        key = request.model_dump(mode='json')
        with self.lock:
            for job in self.jobs.values():
                if job['request'] == key and job['status'] in ('queued', 'running'):
                    return dict(job)
            if sum(j['status'] in ('queued', 'running') for j in self.jobs.values()) >= 3:
                raise HTTPException(429, 'Đang xử lý nhiều báo cáo. Vui lòng thử lại sau.')
            if len(self.jobs) >= 100:
                done = next((i for i,j in self.jobs.items() if j['status'] in ('completed','failed')), None)
                if done:
                    del self.jobs[done]
            job = dict(id=str(uuid4()), status='queued', request=key)
            self.jobs[job['id']] = job
            result = dict(job)
        self.executor.submit(self.run, job['id'], request)
        return result

    def run(self, job_id, request):
        with self.lock:
            self.jobs[job_id]['status'] = 'running'
        try:
            results = generate_reports(self.settings, request)
            update = dict(status='completed', results=results)
        except ValueError as error:
            update = dict(status='failed', error=str(error))
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Report generation failed')
            update = dict(status='failed', error='Không thể tạo báo cáo. Kiểm tra nhật ký và dữ liệu nguồn.')
        with self.lock:
            self.jobs[job_id].update(update)

    def get(self, job_id):
        with self.lock:
            return dict(self.jobs[job_id]) if job_id in self.jobs else None

    def stop(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


def generation_router(settings, catalog, templates, jobs):
    router = APIRouter()

    @router.post('/api/report-jobs', status_code=202)
    def generate(request: Request, body: GenerationRequest):
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Yêu cầu phải được gửi từ giao diện của ứng dụng.')
        if request.headers.get('content-type','').split(';')[0] != 'application/json':
            raise HTTPException(415, 'Cần gửi dữ liệu JSON.')
        return jobs.submit(body)

    @router.get('/api/report-jobs/{job_id}')
    def status(job_id: str):
        result = jobs.get(job_id)
        if result is None:
            raise HTTPException(404, 'Không tìm thấy tác vụ.')
        return result

    def lookup(report_id):
        try:
            record = catalog.get(report_id)
        except ValueError:
            record = None
        if record is None:
            raise HTTPException(404, 'Không tìm thấy báo cáo.')
        return record, report_analysis(settings, report_id, catalog)

    @router.get('/reports/{report_id}')
    def detail(request: Request, report_id: str):
        record, analysis = lookup(report_id)
        return templates.TemplateResponse(request=request, name='report_detail.html',
            context=dict(report=record, analysis=analysis, active='reports',
                         labels={'stock':'Cổ phiếu','industry':'Ngành','macro':'Vĩ mô'}))

    @router.get('/api/reports/{report_id}/analysis')
    def analysis(report_id: str):
        _, payload = lookup(report_id)
        if payload is None:
            raise HTTPException(404, 'Báo cáo chưa có bản phân tích đính kèm.')
        return {key:payload[key] for key in ('document','page_count')}

    return router
