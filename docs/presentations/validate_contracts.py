#!/usr/bin/env python3
"""Validate draft presentation examples; no production I/O or generation occurs.

Requires Python 3.11+ and jsonschema. This checks contract shape and a selected set
of semantic invariants. Authorization, asset bytes, renderer fidelity, scheduler
execution and full quality policy belong to the implementation, not this tool.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parent
NAMES = ('brand-kit', 'template', 'deck-spec', 'weekly-series', 'generation-manifest')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def unique(rows: list[dict], name: str) -> None:
    ids = [row['id'] for row in rows]
    require(len(set(ids)) == len(ids), f'duplicate {name} ID')


def bounds(box: dict) -> None:
    require(box['x'] + box['w'] <= 1 + 1e-9, 'horizontal bounds exceed parent')
    require(box['y'] + box['h'] <= 1 + 1e-9, 'vertical bounds exceed parent')


def period(value: dict) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(value['start'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(value['end_exclusive'].replace('Z', '+00:00'))
    require(start.tzinfo is not None and end.tzinfo is not None, 'period requires timezone offsets')
    require(start < end, 'period is empty or inverted')
    return start, end


def matches(reference: dict, value: dict) -> None:
    require(reference['id'] == value['id'], 'referenced ID mismatch')
    require(reference['version'] == value['version'], 'referenced version mismatch')
    require(reference['sha256'] == digest(value), 'referenced digest mismatch')


def validate_shapes(bundle: dict, validators: dict) -> None:
    # Reject non-finite values that Python JSON may otherwise accept.
    json.dumps(bundle, allow_nan=False)
    for name in NAMES:
        validators[name].validate(bundle[name])


def validate_semantics(bundle: dict) -> None:
    kit, template, deck, series, manifest = (bundle[name] for name in NAMES)
    require(all(value['fixture_only'] for value in bundle.values()), 'examples must remain fictional')
    require(len({v['company_id'] for v in (kit, template, deck, series)}) == 1,
            'cross-company contract reference')
    require(deck['workspace_id'] == series['workspace_id'], 'workspace reference mismatch')
    for value in (template, deck, series, manifest):
        matches(value['brand_ref'], kit)
    for value in (deck, series, manifest):
        matches(value['template_ref'], template)
    require(deck['slide_size'] == template['slide_size'] == kit['slide_size'], 'slide size mismatch')
    for font in kit['typography'].values():
        require(font['minimum_pt'] <= font['preferred_pt'], 'preferred type size below minimum')
        require(font['family'] in kit['allowed_fonts'], 'unapproved font family')
        require(set(font['fallbacks']).issubset(kit['allowed_fonts']), 'unapproved fallback font')
    logo_ids = [logo['asset_id'] for logo in kit['logos']]
    require(len(logo_ids) == len(set(logo_ids)), 'duplicate logo asset ID')
    require(all(logo['rights'] == 'fixture_placeholder' for logo in kit['logos']),
            'fixtures must not pretend to contain licensed company logos')
    if template['mode'] == 'curated':
        require(template['original_asset_id'] is None, 'curated fixture has an original import')
        require(template['fidelity']['status'] == 'not_applicable', 'curated fidelity mismatch')
    else:
        require(template['original_asset_id'] is not None, 'import requires original asset reference')
    unique(template['layouts'], 'layout')
    layouts = {layout['id']: layout for layout in template['layouts']}
    for layout in layouts.values():
        unique(layout['placeholders'], 'placeholder')
        for placeholder in layout['placeholders']:
            bounds(placeholder['bounds'])
    unique(deck['slides'], 'slide')
    count = len(deck['slides'])
    if 'exact' in deck['slide_count']:
        require(count == deck['slide_count']['exact'], 'exact slide count mismatch')
    else:
        lo, hi = deck['slide_count']['minimum'], deck['slide_count']['maximum']
        require(lo <= count <= hi, 'slide count range mismatch')
    deck_start, deck_end = period(deck['period'])
    unique(deck['sources'], 'source snapshot')
    sources = {source['id']: source for source in deck['sources']}
    metrics = {}
    for source in sources.values():
        require(source['fixture_only'], 'source fixture lacks fictional declaration')
        period(source['period'])
        unique(source['metrics'], 'metric')
        for metric in source['metrics']:
            require(metric['period_key'] == source['period']['key'], 'metric period mismatch')
            require(math.isfinite(metric['value']), 'non-finite metric')
            metrics[source['id'], metric['id']] = metric

    def resolve(reference: dict, expected: float | None = None, unit: str | None = None) -> dict:
        key = reference['source_snapshot_id'], reference['metric_id']
        require(key in metrics, 'unknown metric reference')
        metric = metrics[key]
        if expected is not None:
            require(expected == metric['value'], 'visible number differs from source metric')
        if unit is not None:
            require(unit == metric['unit'], 'visible unit differs from source metric')
        return metric

    element_ids = set()
    claim_ids = set()
    for slide in deck['slides']:
        require(slide['layout_id'] in layouts, 'unknown layout')
        note_sources = set(slide['notes']['source_snapshot_ids'])
        require(note_sources.issubset(sources), 'unknown notes source')
        used_sources = set()
        unique(slide['claims'], 'claim')
        local_claims = {claim['id'] for claim in slide['claims']}
        require(not (claim_ids & local_claims), 'duplicate claim ID across slides')
        claim_ids.update(local_claims)
        for claim in slide['claims']:
            numeric = 'numeric_value' in claim
            require(not numeric or all(k in claim for k in ('metric_ref', 'unit')),
                    'numeric claim lacks metric reference/unit')
            if 'metric_ref' in claim:
                require(claim['classification'] == 'observed', 'assumption masquerades as observed metric')
                resolve(claim['metric_ref'], claim.get('numeric_value'), claim.get('unit'))
                used_sources.add(claim['metric_ref']['source_snapshot_id'])
        unique(slide['elements'], 'element')
        for element in slide['elements']:
            require(element['id'] not in element_ids, 'duplicate element ID across slides')
            element_ids.add(element['id'])
            bounds(element['bounds'])
            kind = element['kind']
            if kind == 'text':
                require(set(element['claim_ids']).issubset(local_claims), 'unknown text claim')
            elif kind == 'chart':
                for chart_series in element['series']:
                    require(len(chart_series['points']) == len(element['categories']),
                            'chart categories and points differ')
                    for point in chart_series['points']:
                        resolve(point['metric_ref'], point['value'], element['unit'])
                        used_sources.add(point['metric_ref']['source_snapshot_id'])
                if element['chart_type'] in ('bar', 'column'):
                    require(element['axis_zero_baseline'], 'fixture bar chart requires zero baseline')
            elif kind == 'table':
                for row in element['rows']:
                    require(len(row) == len(element['headers']), 'ragged table row')
                    for cell in row:
                        if isinstance(cell['value'], (int, float)):
                            require('metric_ref' in cell, 'numeric table cell lacks evidence')
                        if 'metric_ref' in cell:
                            resolve(cell['metric_ref'], cell['value'] if isinstance(cell['value'], (int, float)) else None)
                            used_sources.add(cell['metric_ref']['source_snapshot_id'])
            elif kind == 'diagram':
                require(element['source_snapshot_id'] in sources, 'unknown diagram source')
                require(sources[element['source_snapshot_id']]['kind'] in ('dmind_snapshot', 'matrix_snapshot'),
                        'diagram source is not a graph snapshot')
                unique(element['nodes'], 'diagram node')
                unique(element['edges'], 'diagram edge')
                nodes = {node['id'] for node in element['nodes']}
                for node in element['nodes']:
                    bounds(node['bounds'])
                for edge in element['edges']:
                    require(edge['from'] in nodes and edge['to'] in nodes, 'dangling diagram edge')
                used_sources.add(element['source_snapshot_id'])
            elif kind == 'image':
                require(element['provenance'] == 'fixture_placeholder', 'fixture cannot claim real imagery')
        require(used_sources.issubset(note_sources), 'used evidence absent from slide notes')

    try:
        zone = ZoneInfo(series['timezone'])
    except ZoneInfoNotFoundError as exc:
        raise ValueError('unknown IANA timezone') from exc
    lo, hi = series['slide_count']['minimum'], series['slide_count']['maximum']
    require(lo <= hi and lo <= count <= hi, 'weekly slide count mismatch')
    require(not series['schedule']['enabled'], 'fixture must not enable a schedule')
    require(len(series['source_ids']) == len(set(series['source_ids'])), 'duplicate series source')
    require({source['source_id'] for source in sources.values()}.issubset(series['source_ids']),
            'source snapshot outside series scope')
    unique(series['sections'], 'weekly section')
    local_start, local_end = deck_start.astimezone(zone), deck_end.astimezone(zone)
    require(local_start.weekday() == series['reporting_rule']['week_starts_on'], 'weekly start weekday mismatch')
    require(local_start.hour == local_start.minute == local_start.second == 0, 'weekly start must be local midnight')
    require(local_end.hour == local_end.minute == local_end.second == 0, 'weekly end must be local midnight')
    require((local_end.date() - local_start.date()).days == 7, 'calendar week is not seven local dates')
    require(manifest['deck_id'] == deck['id'], 'manifest deck mismatch')
    require(manifest['deck_spec_sha256'] == digest(deck), 'manifest spec digest mismatch')
    unique(manifest['source_snapshot_hashes'], 'manifest source')
    require({s['id']: s['sha256'] for s in manifest['source_snapshot_hashes']} ==
            {s['id']: s['sha256'] for s in sources.values()}, 'manifest source hashes mismatch')
    unique(manifest['outputs'], 'output artifact')
    pptx = [output for output in manifest['outputs'] if output['kind'] == 'pptx']
    require(len(pptx) == 1 and pptx[0]['sha256'] == manifest['quality']['pptx_sha256'],
            'quality bound to wrong export')
    quality = manifest['quality']
    require(quality['total_slides'] == count, 'quality slide count mismatch')
    require(quality['slides_reviewed'] <= count, 'impossible review coverage')
    if quality['status'] == 'review_ready':
        require(quality['hard_failure_count'] == 0 and quality['slides_reviewed'] == count and
                quality['receipt_id'] is not None and quality['review_method'] != 'none',
                'review-ready status lacks proof')
    require(quality['status'] == 'not_evaluated' and quality['receipt_id'] is None and
            quality['slides_reviewed'] == 0, 'fictional manifest cannot claim an actual quality review')


def load() -> tuple[dict, dict]:
    validators, bundle = {}, {}
    for name in NAMES:
        schema = json.loads((ROOT / 'schemas' / f'{name}.schema.json').read_text())
        Draft202012Validator.check_schema(schema)
        validators[name] = Draft202012Validator(schema, format_checker=FormatChecker())
        bundle[name] = json.loads((ROOT / 'examples' / f'{name}.example.json').read_text())
    return bundle, validators


def main() -> None:
    bundle, validators = load()
    validate_shapes(bundle, validators)
    validate_semantics(bundle)
    probes = [
        ('cross-company', lambda b: b['deck-spec'].update(company_id='company_other')),
        ('digest', lambda b: b['deck-spec']['brand_ref'].update(sha256='e' * 64)),
        ('count', lambda b: b['deck-spec']['slide_count'].update(exact=7)),
        ('bounds', lambda b: b['deck-spec']['slides'][0]['elements'][1]['bounds'].update(x=.8)),
        ('evidence', lambda b: b['deck-spec']['slides'][1]['elements'][1]['series'][0]['points'][0].update(value=400)),
        ('metric reference', lambda b: b['deck-spec']['slides'][1]['claims'][0]['metric_ref'].update(metric_id='unknown')),
        ('units', lambda b: b['deck-spec']['slides'][1]['elements'][1].update(unit='USD')),
        ('chart categories', lambda b: b['deck-spec']['slides'][1]['elements'][1]['categories'].pop()),
        ('numeric table', lambda b: b['deck-spec']['slides'][2]['elements'][1]['rows'][0][1].pop('metric_ref')),
        ('diagram edge', lambda b: b['deck-spec']['slides'][3]['elements'][1]['edges'][0].update(to='unknown')),
        ('notes citation', lambda b: b['deck-spec']['slides'][1]['notes'].update(source_snapshot_ids=[])),
        ('timezone', lambda b: b['weekly-series'].update(timezone='Unknown/Nowhere')),
        ('fixture schedule', lambda b: b['weekly-series']['schedule'].update(enabled=True)),
        ('range', lambda b: b['weekly-series']['slide_count'].update(minimum=20, maximum=10)),
        ('review proof', lambda b: b['generation-manifest']['quality'].update(status='review_ready')),
        ('client approval', lambda b: b['deck-spec'].update(approved=True)),
        ('unknown executable', lambda b: b['deck-spec'].update(javascript='untrusted code')),
        ('duplicate element', lambda b: b['deck-spec']['slides'][0]['elements'][1].update(id='slide_cover_title')),
        ('font', lambda b: b['brand-kit']['typography']['body'].update(family='UnavailableFont')),
        ('window', lambda b: b['deck-spec']['period'].update(end_exclusive='2026-09-19T22:00:00Z')),
    ]
    for label, mutate in probes:
        candidate = copy.deepcopy(bundle)
        mutate(candidate)
        # Keep audit digests in sync for semantic probes so an unrelated hash
        # mismatch cannot mask the intended invalid input. The digest probe
        # deliberately retains its bad reference.
        if label != 'digest':
            kit = candidate['brand-kit']
            for value in (candidate['template'], candidate['deck-spec'],
                          candidate['weekly-series'], candidate['generation-manifest']):
                value['brand_ref']['sha256'] = digest(kit)
            template = candidate['template']
            for value in (candidate['deck-spec'], candidate['weekly-series'],
                          candidate['generation-manifest']):
                value['template_ref']['sha256'] = digest(template)
            candidate['generation-manifest']['deck_spec_sha256'] = digest(candidate['deck-spec'])
        try:
            validate_shapes(candidate, validators)
            validate_semantics(candidate)
        except (ValueError, ValidationError):
            continue
        raise AssertionError(f'invalid contract accepted: {label}')
    print(f'Validated {len(NAMES)} draft schemas, {len(NAMES)} fictional fixtures and {len(probes)} rejection probes.')


if __name__ == '__main__':
    main()
