"""Wire schema verified against the public DNSE priceboard on 2026-10-09.

Only public sector statistics are decoded; account/trading message types are excluded.
"""

from functools import lru_cache

from google.protobuf import descriptor_pb2, message_factory


@lru_cache(maxsize=1)
def sector_messages():
    file = descriptor_pb2.FileDescriptorProto(name='dnse_sector.proto', package='research_dnse', syntax='proto3')
    field = descriptor_pb2.FieldDescriptorProto

    def message(name, fields):
        model = file.message_type.add(name=name)
        for number, key, kind, repeated in fields:
            value = model.field.add(name=key, number=number,
                label=field.LABEL_REPEATED if repeated else field.LABEL_OPTIONAL)
            if isinstance(kind, str):
                value.type, value.type_name = field.TYPE_MESSAGE, '.research_dnse.' + kind
            else:
                value.type = kind

    message('Envelope', [(1, 'type', field.TYPE_INT32, False), (2, 'payload', field.TYPE_BYTES, False)])
    message('Timestamp', [(1, 'seconds', field.TYPE_INT64, False), (2, 'nanos', field.TYPE_INT32, False)])
    message('Sector', [
        (1, 'id', field.TYPE_STRING, False), (2, 'slug', field.TYPE_STRING, False),
        (3, 'name', field.TYPE_STRING, False), (4, 'priceVolatilityKey', field.TYPE_STRING, True),
        (5, 'priceVolatilityValue', field.TYPE_DOUBLE, True), (6, 'matchPrice', field.TYPE_DOUBLE, False),
        (7, 'volume', field.TYPE_DOUBLE, False), (8, 'marketCap', field.TYPE_DOUBLE, False),
        (9, 'totalStocks', field.TYPE_INT32, False), (10, 'priceChangeToday', field.TYPE_DOUBLE, False),
        (11, 'grossTradeValue', field.TYPE_DOUBLE, False), (12, 'time', 'Timestamp', False)])
    message('Snapshot', [
        (1, 'data', 'Sector', True), (2, 'time', 'Timestamp', False),
        (3, 'priceVolatilityKey', field.TYPE_STRING, True), (4, 'priceVolatilityValue', field.TYPE_DOUBLE, True),
        (5, 'matchPrice', field.TYPE_DOUBLE, False), (6, 'volume', field.TYPE_DOUBLE, False),
        (7, 'marketCap', field.TYPE_DOUBLE, False), (8, 'totalStocks', field.TYPE_INT32, False),
        (9, 'grossTradeValue', field.TYPE_DOUBLE, False)])
    return message_factory.GetMessages([file])
