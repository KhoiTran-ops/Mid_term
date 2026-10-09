"""Persist DNSE sector snapshots and company classification with raw provenance."""

import asyncio
from datetime import datetime, UTC
import json
from pathlib import Path

import httpx

from stock_reports.data_sources.archive import ResponseArchive
from stock_reports.data_sources.dnse.sectors import SECTOR_API, SECTOR_BROKER, SECTOR_TOPIC, decode_sector_packet, fetch_sector_packet
from stock_reports.storage.industries import IndustryStore


def update_industries(settings, *, refresh_catalog=True) -> dict:
    store = IndustryStore(settings.industries_database)
    started = datetime.now(UTC)
    run_directory = settings.runs_directory / ('industries-' + started.strftime('%Y%m%dT%H%M%S%f'))
    archive = ResponseArchive(run_directory / 'raw')
    result = dict(status='running', started_at=started.isoformat(), database=str(store.database))
    manifest = run_directory / 'manifest.json'
    manifest.write_text(json.dumps(result), encoding='utf-8')
    try:
        if refresh_catalog:
            with httpx.Client(timeout=30) as client:
                def read(path, params):
                    response = client.get(SECTOR_API + path, params=params)
                    response.raise_for_status()
                    archive.save('dnse-industries', str(response.url), response.content, '.json')
                    payload = response.json()
                    if not isinstance(payload.get('data'), list) or len(payload['data']) != payload.get('total'):
                        raise ValueError('DNSE catalog is incomplete or its schema changed')
                    return payload['data']

                sectors = read('/sectors', {'classificationType': 'gics', 'level': 2})
                if not sectors or any(s.get('classificationType') != 'gics' or s.get('level') != 2 for s in sectors):
                    raise ValueError('Unexpected DNSE classification level')
                companies = read('/tickers', {'_start': 0, '_end': 10000, 'floor': ''})
                store.save_catalog(sectors, companies, retrieved_at=datetime.now(UTC).isoformat())
        packet = asyncio.run(fetch_sector_packet())
        archive.save('dnse-industries', SECTOR_BROKER + '#' + SECTOR_TOPIC, packet, '.mqtt')
        rows, source_time = decode_sector_packet(packet)
        store.save_snapshot(rows, source_time=source_time, retrieved_at=datetime.now(UTC).isoformat())
        result.update(status='completed', received_sectors=len(rows), source_time=source_time, **store.summary())
        return result
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        raise
    finally:
        result['completed_at'] = datetime.now(UTC).isoformat()
        manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
