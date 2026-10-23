import copy
import datetime as dt
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lol_lookup', ROOT / 'scripts/lol.py')
lol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lol)


class LookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = lol.load_data()

    def test_dataset_references_resolve(self):
        self.assertEqual(lol.validate(self.data), [])

    def test_exact_number_beats_mentions(self):
        result = lol.search(self.data, '4396')
        self.assertEqual(result[0]['id'], 'damage-4396')

    def test_fullwidth_and_punctuation(self):
        self.assertEqual(lol.search(self.data, '１５：５７')[0]['id'], 'time-1557')

    def test_player_alias_finds_related_events(self):
        result = lol.search(self.data, '阿水', limit=99)
        self.assertIn('vietnam-curd', {r['id'] for r in result})

    def test_multiple_terms_use_and(self):
        result = lol.search(self.data, '阿水 越南', limit=99)
        self.assertIn('vietnam-curd', {r['id'] for r in result})
        self.assertNotIn('time-1557', {r['id'] for r in result})

    def test_provisional_opt_in(self):
        self.assertEqual(lol.search(self.data, '见过烟位吗'), [])
        self.assertEqual(lol.search(self.data, '见过烟位吗', include_provisional=True)[0]['evidence'], 'provisional')

    def test_current_year_filter(self):
        result = lol.search(self.data, 'BLG', year=2026)
        self.assertTrue(result)
        self.assertTrue(all(r['year'] == 2026 for r in result))

    def test_date_filters_future_event(self):
        self.assertEqual(lol.search(self.data, '六冠王', cutoff=dt.date(2025, 11, 8)), [])
        self.assertTrue(lol.search(self.data, '六冠王', cutoff=dt.date(2025, 11, 9)))

    def test_unknown_event_date_conservative_year_end(self):
        event = next(e for e in self.data['memes'] if e['id'] == 'damage-4396')
        self.assertFalse(lol.available_by(event, dt.date(2016, 10, 1)))
        self.assertTrue(lol.available_by(event, dt.date(2016, 12, 31)))

    def test_timeless_terms_remain_available(self):
        self.assertTrue(lol.search(self.data, '补刀', cutoff=dt.date(2011, 1, 1)))

    def test_heat_and_kind_filter(self):
        result = lol.search(self.data, '资源', kind='mechanic', heat=0)
        self.assertTrue(result)
        self.assertTrue(all(r['kind'] == 'mechanic' and r['heat'] == 0 for r in result))

    def test_unknown_query_does_not_fabricate(self):
        self.assertEqual(lol.search(self.data, '不存在的神秘梗abc987xyz'), [])

    def test_short_alias_does_not_match_inside_words(self):
        self.assertNotIn('t1', lol.resolve_entities('t12345', self.data['entities']))
        self.assertNotIn('edg', lol.resolve_entities('电子榨菜', self.data['entities']))

    def test_json_cli_is_machine_readable(self):
        run = subprocess.run([sys.executable, str(ROOT / 'scripts/lol.py'), 'search', '4396', '--json'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)[0]['id'], 'damage-4396')
        self.assertEqual(run.stderr, '')

    def test_bad_date_cli_has_actionable_error(self):
        run = subprocess.run([sys.executable, str(ROOT / 'scripts/lol.py'), 'search', '冠军', '--as-of', '2026-02-30'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn('YYYY-MM-DD', run.stderr)

    def test_broken_reference_is_detected(self):
        broken = copy.deepcopy(self.data)
        broken['memes'][0]['sources'] = ['missing-source']
        self.assertTrue(any('来源不存在' in e for e in lol.validate(broken)))

    def test_impossible_event_chronology_is_detected(self):
        broken = copy.deepcopy(self.data)
        broken['memes'][0]['event_date'] = '2030-01-01'
        self.assertTrue(any('日期冲突' in e for e in lol.validate(broken)))

    def test_aliases_do_not_confuse_namesake_champion(self):
        resolved = lol.resolve_entities('娜美辅助英雄', self.data['entities'])
        self.assertNotIn('namei', resolved)
        self.assertIn('nami', resolved)


if __name__ == '__main__':
    unittest.main()
