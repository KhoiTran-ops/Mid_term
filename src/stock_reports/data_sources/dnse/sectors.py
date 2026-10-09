"""Public DNSE industry catalog and retained MQTT 5 sector snapshot."""

import asyncio
from datetime import datetime, UTC
import math
from uuid import uuid4

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
import websockets

from stock_reports.data_sources.dnse.sector_schema import sector_messages


SECTOR_BROKER = 'wss://datafeed-krx.dnse.com.vn/wss'
SECTOR_TOPIC = 'stats/sector/volatility'
SECTOR_API = 'https://api.dnse.com.vn/market-api'


def mqtt_varint(value: int) -> bytes:
    if not 0 <= value <= 268435455:
        raise ValueError('Invalid MQTT integer')
    output = bytearray()
    while value >= 128:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def read_varint(data, position):
    value = 0
    for offset in range(4):
        if position >= len(data):
            raise ValueError('Truncated MQTT integer')
        byte = data[position]
        position += 1
        value |= (byte & 127) << (7 * offset)
        if not byte & 128:
            return value, position
    raise ValueError('Invalid MQTT integer')


def mqtt_string(value: str) -> bytes:
    encoded = value.encode('utf-8')
    return len(encoded).to_bytes(2, 'big') + encoded


def mqtt_body(packet: bytes, expected_type: int) -> bytes:
    if not packet or packet[0] >> 4 != expected_type:
        raise ValueError('Unexpected MQTT packet')
    remaining, position = read_varint(packet, 1)
    if remaining != len(packet) - position:
        raise ValueError('Truncated or combined MQTT packet')
    return packet[position:]


def decode_sector_packet(packet: bytes) -> tuple[list[dict], str]:
    body = mqtt_body(packet, 3)
    if packet[0] & 6 or len(body) < 3:
        raise ValueError('Sector reader requires QoS 0')
    size = int.from_bytes(body[:2], 'big')
    if body[2:2+size].decode('utf-8') != SECTOR_TOPIC:
        raise ValueError('Unexpected public data topic')
    properties, position = read_varint(body, 2+size)
    position += properties
    if position >= len(body):
        raise ValueError('Missing sector payload')
    classes = sector_messages()
    try:
        envelope = classes['research_dnse.Envelope'].FromString(body[position:])
        if envelope.type != 730:
            raise ValueError('Unexpected DNSE event type')
        snapshot = classes['research_dnse.Snapshot'].FromString(envelope.payload)
    except DecodeError as error:
        raise ValueError('Invalid DNSE sector schema') from error
    rows = [MessageToDict(row, preserving_proto_field_name=True) for row in snapshot.data]
    if not rows or not snapshot.HasField('time') or snapshot.time.seconds <= 0:
        raise ValueError('Sector snapshot has no records or source timestamp')
    for row in rows:
        keys, values = row.get('priceVolatilityKey', []), row.get('priceVolatilityValue', [])
        if not row.get('id') or len(keys) != len(values) or not all(math.isfinite(v) for v in values):
            raise ValueError('Sector snapshot schema changed')
    source_time = datetime.fromtimestamp(snapshot.time.seconds + snapshot.time.nanos/1e9, UTC).isoformat()
    return rows, source_time


async def fetch_sector_packet(timeout=20) -> bytes:
    # Read one retained public snapshot; this client has no account/auth channels.
    async with asyncio.timeout(timeout):
        async with websockets.connect(SECTOR_BROKER, subprotocols=['mqtt'],
                origin='https://banggia.dnse.com.vn', open_timeout=10, max_size=6_000_000) as socket:
            connect = mqtt_string('MQTT') + bytes([5, 2, 0, 20, 0]) + mqtt_string('research-' + uuid4().hex[:12])
            await socket.send(b'\x10' + mqtt_varint(len(connect)) + connect)
            ack = mqtt_body(await socket.recv(), 2)
            if len(ack) < 2 or ack[1] != 0:
                raise ValueError('DNSE rejected the public MQTT connection')
            subscribe = b'\x00\x01\x00' + mqtt_string(SECTOR_TOPIC) + b'\x00'
            await socket.send(b'\x82' + mqtt_varint(len(subscribe)) + subscribe)
            while True:
                packet = await socket.recv()
                if not isinstance(packet, bytes) or not packet:
                    raise ValueError('Unexpected MQTT transport format')
                if packet[0] >> 4 == 9:
                    suback = mqtt_body(packet, 9)
                    properties, cursor = read_varint(suback, 2)
                    codes = suback[cursor+properties:]
                    if not codes or any(code >= 128 for code in codes):
                        raise ValueError('DNSE rejected sector subscription')
                elif packet[0] >> 4 == 3:
                    decode_sector_packet(packet)
                    await socket.send(b'\xe0\x00')
                    return packet
