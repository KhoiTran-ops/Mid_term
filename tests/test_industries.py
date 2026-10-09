from datetime import datetime, UTC
import json
import struct

import pytest

from stock_reports.data_sources.dnse.sectors import decode_sector_packet, mqtt_varint, mqtt_string
from stock_reports.storage.industries import IndustryStore


def varint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out + bytes([value]))


def binary_field(number, value):
    return varint(number * 8 + 2) + varint(len(value)) + value


def sector_fixture():
    sector = binary_field(1, b'12') + binary_field(2, b'ngan-hang') + binary_field(3, 'Ngân hàng'.encode())
    sector += binary_field(4, b'1d') + binary_field(4, b'1w')
    sector += binary_field(5, struct.pack('<dd', 0.0012, 0.02))
    sector += bytes([9*8]) + varint(27)
    timestamp = bytes([8]) + varint(1791532000)
    data = binary_field(1, sector) + binary_field(2, timestamp)
    envelope = bytes([8]) + varint(730) + binary_field(2, data)
    body = mqtt_string('stats/sector/volatility') + b'\x00' + envelope
    return b'\x31' + mqtt_varint(len(body)) + body


def test_decodes_packed_sector_statistics_without_inventing_missing_price():
    rows, source_time = decode_sector_packet(sector_fixture())
    assert source_time.endswith('+00:00')
    assert len(rows) == 1
    assert rows[0]['id'] == '12'
    assert rows[0]['priceVolatilityKey'] == ['1d', '1w']
    assert rows[0]['priceVolatilityValue'] == pytest.approx([0.0012, 0.02])
    assert 'matchPrice' not in rows[0]
    with pytest.raises(ValueError):
        decode_sector_packet(b'\x31\xff')


def test_industry_store_keys_classification_and_keeps_snapshots_and_company_membership(tmp_path):
    store = IndustryStore(tmp_path / 'industries.db')
    sectors = [dict(sectorId='12', slug='ngan-hang', name='Ngân hàng', level=2, classificationType='gics')]
    companies = [dict(symbol='VCB', floor='HOSE', type='STOCK', isListed=True, gicsIndustryGroupId='12', companyName='Vietcombank')]
    store.save_catalog(sectors, companies, retrieved_at=datetime.now(UTC).isoformat())
    rows, source_time = decode_sector_packet(sector_fixture())
    store.save_snapshot(rows, source_time=source_time, retrieved_at=datetime.now(UTC).isoformat())
    store.save_snapshot(rows, source_time=source_time, retrieved_at=datetime.now(UTC).isoformat())
    data = store.summary()
    assert data['sectors'] == 1 and data['companies'] == 1 and data['snapshots'] == 1
    assert store.list_companies(exchange='HOSE')[0]['industry_id'] == '12'
    assert json.loads(store.latest_snapshots()[0]['raw_json'])['id'] == '12'
