#!/usr/bin/env python3
"""Offline lookup for LOL串子. Python 3.9+, standard library only."""

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = ('meme', 'slang', 'mechanic')
EVIDENCE = ('verified', 'community', 'glossary', 'provisional')


def normalize(value):
    text = unicodedata.normalize('NFKC', str(value)).casefold()
    return ''.join(c for c in text if c.isalnum())


def load_data(directory=None):
    folder = Path(directory) if directory else ROOT / 'data'
    return {name: json.loads((folder / (name + '.json')).read_text(encoding='utf-8'))
            for name in ('memes', 'entities', 'sources')}


def date_value(value):
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('日期需为有效的 YYYY-MM-DD') from exc


def natural(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('必须是正整数')
    return number


def available_by(entry, cutoff):
    if cutoff is None:
        return True
    if entry.get('event_date'):
        return dt.date.fromisoformat(entry['event_date']) <= cutoff
    year = entry.get('year')
    return year is None or dt.date(year, 12, 31) <= cutoff


def resolve_entities(query, entities):
    """Exact alias matches support short IDs; embedded aliases need 2+ chars."""
    normalized = normalize(query)
    matches = set()
    for entity in entities:
        for alias in [entity['id'], entity['name']] + entity['aliases']:
            name = normalize(alias)
            if entity['id'] == 'namei' and alias in ('娜美', '那美') and any(
                cue in query for cue in ('英雄', '技能', '鲛姬')
            ):
                continue
            if entity['id'] == 'doran' and alias == '多兰' and any(
                cue in query for cue in ('多兰剑', '多兰盾', '多兰戒', '装备')
            ):
                continue
            if name == normalized:
                matches.add(entity['id'])
            elif len(name) >= 2 and name in normalized:
                # Avoid matching short Latin names within unrelated words.
                if name.isascii() and not re.search(
                    r'(?<![a-z0-9])' + re.escape(alias.casefold()) + r'(?![a-z0-9])',
                    unicodedata.normalize('NFKC', query).casefold(),
                ):
                    continue
                matches.add(entity['id'])
    return matches


def token_score(token, entry, entity_ids):
    needle = normalize(token)
    if needle == normalize(entry['term']):
        return 120
    if needle in {normalize(a) for a in entry['aliases']}:
        return 110
    score = 0
    if entity_ids.intersection(entry['subjects']):
        score += 35
    fields = [('term', 45), ('meaning', 15), ('context', 9), ('use_when', 4)]
    for name, weight in fields:
        if needle in normalize(entry[name]):
            score += weight
    if any(needle in normalize(a) for a in entry['aliases']):
        score += 30
    if any(needle in normalize(tag) for tag in entry['tags']):
        score += 20
    return score


def search(data, query, *, kind=None, year=None, heat=3, cutoff=None,
           include_provisional=False, limit=8):
    if not normalize(query):
        return []
    tokens = [part for part in query.split() if normalize(part)]
    # Space-separated keywords use AND; a single phrase stays a single query.
    resolved = [resolve_entities(token, data['entities']) for token in tokens]
    results = []
    for entry in data['memes']:
        if kind and entry['kind'] != kind:
            continue
        if year is not None and entry['year'] != year:
            continue
        if entry['heat'] > heat or not available_by(entry, cutoff):
            continue
        if entry['evidence'] == 'provisional' and not include_provisional:
            continue
        scores = [token_score(token, entry, linked) for token, linked in zip(tokens, resolved)]
        if not scores or not all(scores):
            continue
        item = dict(entry)
        item['score'] = sum(scores)
        results.append(item)
    results.sort(key=lambda item: (-item['score'], item['id']))
    source_map = {source['id']: source for source in data['sources']}
    for item in results:
        item['source_details'] = [source_map[sid] for sid in item['sources']]
    return results[:limit]


def validate(data):
    errors = []
    for name, rows in data.items():
        if not isinstance(rows, list):
            errors.append(f'{name}: 顶层必须是数组')
            continue
        ids = [row.get('id') for row in rows if isinstance(row, dict)]
        if len(ids) != len(rows) or any(not sid for sid in ids):
            errors.append(f'{name}: 每条记录必须有ID')
        duplicates = [sid for sid, count in Counter(ids).items() if count > 1]
        if duplicates:
            errors.append(f'{name}: 重复ID {duplicates}')
    if errors:
        return errors
    source_ids = {s['id'] for s in data['sources']}
    entity_ids = {e['id'] for e in data['entities']}
    for source in data['sources']:
        if not re.match(r'^https://[^/\s]+', source.get('url', '')):
            errors.append(f'{source["id"]}: 来源需使用HTTPS链接')
        if source.get('access') not in ('full_text', 'excerpt', 'video_metadata'):
            errors.append(f'{source["id"]}: access不合法')
        if not source.get('supports'):
            errors.append(f'{source["id"]}: 缺少支持范围')
    for entity in data['entities']:
        if not entity.get('name') or not isinstance(entity.get('aliases'), list):
            errors.append(f'{entity["id"]}: 人物/队伍记录不完整')
    required = ('term', 'aliases', 'kind', 'year', 'subjects', 'tags', 'meaning',
                'context', 'use_when', 'avoid', 'heat', 'evidence', 'sources', 'checked_at')
    for entry in data['memes']:
        eid = entry['id']
        missing = [key for key in required if key not in entry]
        if missing:
            errors.append(f'{eid}: 缺少 {missing}')
            continue
        for field in ('aliases', 'subjects', 'tags', 'sources'):
            if not isinstance(entry[field], list) or any(not isinstance(x, str) for x in entry[field]):
                errors.append(f'{eid}: {field}需为字符串数组')
        if any(not isinstance(entry[field], list) for field in ('aliases', 'subjects', 'tags', 'sources')):
            continue
        for sid in entry['sources']:
            if sid not in source_ids:
                errors.append(f'{eid}: 来源不存在 {sid}')
        for subject in entry['subjects']:
            if subject not in entity_ids:
                errors.append(f'{eid}: 关联对象不存在 {subject}')
        if entry['kind'] not in KINDS or entry['evidence'] not in EVIDENCE:
            errors.append(f'{eid}: 分类或证据等级不合法')
        if type(entry['heat']) is not int or entry['heat'] not in range(4):
            errors.append(f'{eid}: heat需为0—3')
        year = entry['year']
        if year is not None and (type(year) is not int or not 2009 <= year <= 2100):
            errors.append(f'{eid}: year不合法')
        if entry['evidence'] != 'glossary' and not entry['sources']:
            errors.append(f'{eid}: 典故与待核实记录需要来源')
        for field in ('term', 'meaning', 'context', 'use_when', 'avoid'):
            if not isinstance(entry[field], str) or not entry[field].strip():
                errors.append(f'{eid}: {field}不能为空')
        try:
            checked = dt.date.fromisoformat(entry['checked_at'])
            event = dt.date.fromisoformat(entry['event_date']) if entry.get('event_date') else None
            if event and (event.year != year or event > checked):
                errors.append(f'{eid}: 事件年份或核验日期冲突')
        except (ValueError, TypeError):
            errors.append(f'{eid}: 日期不合法')
    return errors


def summary(data):
    return {
        'entries': len(data['memes']), 'entities': len(data['entities']),
        'sources': len(data['sources']),
        'kinds': dict(Counter(e['kind'] for e in data['memes'])),
        'evidence': dict(Counter(e['evidence'] for e in data['memes'])),
        'checked_at': max(e['checked_at'] for e in data['memes']),
        'note': '统计为本地整理条目；不是全网覆盖率，也不是实时赛果。',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='LOL串子：离线查梗，不联网、不自动生成段子。')
    commands = parser.add_subparsers(dest='command', required=True)
    lookup = commands.add_parser('search', help='查梗、别名与术语；空格分隔关键词为AND')
    lookup.add_argument('query')
    lookup.add_argument('--kind', choices=KINDS)
    lookup.add_argument('--year', type=int)
    lookup.add_argument('--heat', type=int, choices=range(4), default=3)
    lookup.add_argument('--as-of', type=date_value, dest='cutoff')
    lookup.add_argument('--limit', type=natural, default=8)
    lookup.add_argument('--include-provisional', action='store_true')
    lookup.add_argument('--json', action='store_true')
    commands.add_parser('stats', help='数据集统计')
    commands.add_parser('check', help='检查本地记录与交叉引用；不验证外链内容')
    args = parser.parse_args(argv)
    try:
        data = load_data()
        errors = validate(data)
        if errors:
            print(json.dumps({'ok': False, 'errors': errors}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        if args.command in ('check', 'stats'):
            payload = summary(data)
            if args.command == 'check':
                payload['ok'] = True
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if not normalize(args.query):
            parser.error('请输入含文字或数字的查询')
        results = search(data, args.query, kind=args.kind, year=args.year, heat=args.heat,
                         cutoff=args.cutoff, include_provisional=args.include_provisional, limit=args.limit)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        elif not results:
            print('未找到适配条目。试试别名、拆成空格关键词，或联网查新梗；不要编出处。')
        else:
            for item in results:
                print(f'[{item["id"]}] {item["term"]} | {item["year"] or "年代未定"} | {item["evidence"]} | 火力≤{item["heat"]}')
                for key, title in [('meaning', '含义'), ('context', '背景'), ('use_when', '适用'), ('avoid', '别串错')]:
                    print(f'  {title}：{item[key]}')
                for source in item['source_details']:
                    print(f'  来源：{source["title"]} <{source["url"]}> [{source["access"]}]')
                print()
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'数据读取失败：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
