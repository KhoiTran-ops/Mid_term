"""Persist DNSE sector snapshots and company classification with raw provenance."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, UTC
import json

import httpx

from stock_reports.data_sources.archive import ResponseArchive
from stock_reports.data_sources.dnse.sectors import SECTOR_API, SECTOR_BROKER, SECTOR_TOPIC, decode_sector_packet, fetch_sector_packet
from stock_reports.storage.industries import IndustryStore
from stock_reports.storage.market import MarketStore


@dataclass(frozen=True)
class PublicCompanyInstrument:
    """Public DNSE company data in the shape required by data collectors."""

    symbol: str
    exchange: str
    company_name: str
    listed_at: int = 0


def public_company_instruments(store: IndustryStore) -> list[PublicCompanyInstrument]:
    return [PublicCompanyInstrument(
        symbol=str(row['symbol']).upper(),
        exchange=str(row['exchange']).upper(),
        company_name=str(row.get('company_name') or ''),
    ) for row in store.list_companies()]


def refresh_public_catalog(settings, archive: ResponseArchive) -> list[PublicCompanyInstrument]:
    """Fetch public sectors/tickers without DNSE trading credentials."""
    store = IndustryStore(settings.industries_database)
    with httpx.Client(timeout=30) as client:
        def read(path, params):
            response = client.get(SECTOR_API + path, params=params)
            response.raise_for_status()
            archive.save('dnse-industries', str(response.url), response.content, '.json')
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                raise ValueError('DNSE catalog schema changed')
            if payload.get('total') is not None and len(payload['data']) != int(payload['total']):
                raise ValueError('DNSE catalog is incomplete')
            return payload['data']

        sectors = read('/sectors', {'classificationType': 'gics', 'level': 2})
        if not sectors or any(s.get('classificationType') != 'gics' or s.get('level') != 2 for s in sectors):
            raise ValueError('Unexpected DNSE classification level')
        companies = read('/tickers', {'_start': 0, '_end': 10000, 'floor': ''})
    store.save_catalog(sectors, companies, retrieved_at=datetime.now(UTC).isoformat())
    instruments = public_company_instruments(store)
    if not instruments:
        raise ValueError('DNSE returned no listed stock companies')
    return instruments


def update_industries(settings, *, refresh_catalog=True, collect_snapshot=True) -> dict:
    store = IndustryStore(settings.industries_database)
    started = datetime.now(UTC)
    run_directory = settings.runs_directory / ('industries-' + started.strftime('%Y%m%dT%H%M%S%f'))
    archive = ResponseArchive(run_directory / 'raw')
    result = dict(status='running', started_at=started.isoformat(), database=str(store.database))
    manifest = run_directory / 'manifest.json'
    manifest.write_text(json.dumps(result), encoding='utf-8')
    try:
        if refresh_catalog:
            instruments = refresh_public_catalog(settings, archive)
            market_store = MarketStore(settings.market_database)
            market_store.initialize()
            market_store.replace_instruments(instruments, source='dnse-public-catalog')
        else:
            instruments = public_company_instruments(store)
        if collect_snapshot:
            packet = asyncio.run(fetch_sector_packet())
            archive.save('dnse-industries', SECTOR_BROKER + '#' + SECTOR_TOPIC, packet, '.mqtt')
            rows, source_time = decode_sector_packet(packet)
            store.save_snapshot(rows, source_time=source_time, retrieved_at=datetime.now(UTC).isoformat())
            result.update(received_sectors=len(rows), source_time=source_time)
        else:
            result.update(received_sectors=0, source_time=None, snapshot='skipped')
        result.update(status='completed', market_catalog_synced=len(instruments), **store.summary())
        return result
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        raise
    finally:
        result['completed_at'] = datetime.now(UTC).isoformat()
        manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
