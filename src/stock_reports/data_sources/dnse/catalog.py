"""Choose a collection scope without altering the full instrument catalog."""


def select_symbols(catalog, *, exchanges=None, symbols=None) -> list[str]:
    exchanges = {s.upper() for s in exchanges} if exchanges else None
    available = {i.symbol for i in catalog if not exchanges or i.exchange in exchanges}
    requested = {s.strip().upper() for s in symbols} if symbols else available
    unknown = requested - available
    if unknown:
        raise ValueError('Symbols outside the requested exchange/catalog: ' + ', '.join(sorted(unknown)))
    if not requested:
        raise ValueError('No stocks match the collection scope')
    return sorted(requested)
