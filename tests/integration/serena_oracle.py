"""Compare structured native graph identities using PHP symbol case semantics."""

def verify_constructor_reference(graph, owner, interface):
    assert isinstance(graph, dict) and isinstance(graph.get('references'), list), 'Malformed native reference graph'
    source = graph.get('source', {})
    assert isinstance(source.get('symbol'), str) and source['symbol'].lower() == owner.lower(), 'Reference graph belongs to another owner'
    assert isinstance(source.get('member'), str) and source['member'].lower() == '__construct', 'Reference graph belongs to another member'
    signatures = set()
    for edge in graph['references']:
        if edge.get('kind') == 'signature':
            target = edge.get('target', {}).get('symbol')
            assert isinstance(target, str), 'Malformed signature target'
            signatures.add(target.lower())
    assert interface.lower() in signatures, 'Known constructor interface missing from native Signature references'
    return {'owner': source['symbol'], 'signature_targets': sorted(signatures)}
