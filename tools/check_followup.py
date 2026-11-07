#!/usr/bin/env python3
"""Recompute follow-up tables from sanitized observations, without contacting a server."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import json
import math
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9), (a, b)


def verify(root=ROOT):
    payload = json.loads(gzip.decompress((root / 'results/vllm-followup-observations.json.gz').read_bytes()))
    assert payload['schema'] == 1
    c16 = defaultdict(list)
    with (root / 'results/vllm-atomic-c16.csv').open() as f:
        csvrows = list(csv.DictReader(f))
    assert len(csvrows) == len(payload['c16']) == 80
    hashes = {}
    for r, table in zip(payload['c16'], csvrows):
        assert r['native_output_tokens'] == 4096 and r['exact_text'] and r['exact_token_ids']
        assert r['release_groups'] in ([16], [8, 8]) and sum(r['scheduled_prompt_groups']) == 16
        assert len(r['output_text_sha256']) == len(r['output_token_ids_sha256']) == 1
        hs = r['output_text_sha256'], r['output_token_ids_sha256']
        assert hs == hashes.setdefault(r['workload'], hs)
        assert r['elapsed_s'] > 0
        close(r['native_output_tokens'] / r['elapsed_s'], r['aggregate_tok_s'])
        for k in ('elapsed_s', 'aggregate_tok_s'):
            close(r[k], float(table[k]))
        for k in ('block', 'native_output_tokens'):
            assert r[k] == int(table[k])
        for k in ('workload', 'admission'):
            assert r[k] == table[k]
        for k in ('release_groups', 'scheduled_prompt_groups'):
            assert '+'.join(map(str, r[k])) == table[k]
        assert table['exact_text'] == table['exact_token_ids'] == 'True'
        c16[r['workload'], '+'.join(map(str, r['release_groups'])), r['admission']].append(r)
    assert len(c16) == 8 and all(len(v) == 10 for v in c16.values())
    result = {'c16': {}, 'hermes_pilot': {}, 'hermes_fleet': {}, 'context_resume': {}}
    with (root / 'results/vllm-atomic-c8.csv').open() as f:
        c8 = list(csv.DictReader(f))
    assert len(c8) == 120
    assert set(Counter((r['workload'], r['admission'], r['release_groups']) for r in c8).values()) == {10}
    for row in c8:
        assert int(row['native_output_tokens']) == 2048
        assert row['exact_text'] == row['exact_token_ids'] == '1'
        assert math.isclose(2048 / float(row['elapsed_s']), float(row['aggregate_tok_s']), rel_tol=1e-8)
    for key, rows in sorted(c16.items()):
        result['c16']['/'.join(key)] = {
            'median_tok_s': median(r['aggregate_tok_s'] for r in rows),
            'range_tok_s': [min(r['aggregate_tok_s'] for r in rows), max(r['aggregate_tok_s'] for r in rows)],
            'intended_groups_formed': sum(r['release_groups'] == r['scheduled_prompt_groups'] for r in rows),
            'waves': len(rows)}
    calls = Counter()
    for lane, count, workers in [('hermes_pilot', 6, 8), ('hermes_fleet', 15, 16)]:
        assert len(payload[lane]) == count
        groups = defaultdict(list)
        for w in payload[lane]:
            assert len(w['sessions']) == workers + 1
            assert w['checked_workers'] == sum(a['passed'] for a in w['sessions'] if a['role'] == 'worker') == workers
            assert [a['role'] for a in w['sessions']] == ['worker'] * workers + ['foreground']
            for session in w['sessions']:
                assert session['passed'] and session['actual_state'] == session['expected_state']
                assert [e['tool'] for e in session['effects']] == ['read_work_item', 'save_work_result']
                assert session['effects'][1]['args'] == session['expected_state']
                assert len(session['calls']) == 3
                for call in session['calls']:
                    assert call['stream_done'] and call['finish_reason'] in ('stop', 'tool_calls')
                    assert type(call['native_output_tokens']) is int and call['native_output_tokens'] > 0
                    assert 0 <= call['cached_prompt_tokens'] <= call['native_prompt_tokens']
                    assert call['ended_s'] > call['started_s']
                    calls[lane] += 1
                assert [t for c in session['calls'] for t in c['tool_names']] == ['read_work_item', 'save_work_result']
            fg = w['sessions'][-1]
            first = fg['calls'][0]
            close(w['foreground_first_tool_s'], first['first_usable_tool_s'])
            close(w['foreground_checked_s'], fg['checked_s'] - first['started_s'])
            if lane == 'hermes_fleet':
                close(w['worker_wave_s'], max(s['checked_s'] for s in w['sessions'][:-1]))
                assert w['observed_peak_workers'] == w['active_worker_limit']
            else:
                close(w['worker_tasks_per_active_hour'], 3600 * workers / w['worker_wave_s'])
            groups[w['strategy']].append(w)
        for strategy, waves in groups.items():
            rates = []
            for wave in waves:
                rr = [c for a in wave['sessions'] for c in a['calls']]
                rate = sum(c['native_output_tokens'] for c in rr) / (
                    max(c['ended_s'] for c in rr) - min(c['started_s'] for c in rr))
                rates.append(rate)
            result[lane][strategy] = {
                'passed_background': sum(w['checked_workers'] for w in waves), 'passed_foreground': len(waves),
                'pooled_checked_tasks_per_active_hour': 3600 * sum(w['checked_workers'] for w in waves) /
                                                        sum(w['worker_wave_s'] for w in waves),
                'median_checked_tasks_per_active_hour': median(3600 * w['checked_workers'] / w['worker_wave_s'] for w in waves),
                'median_whole_wave_native_output_tok_s': median(rates),
                'median_foreground_first_tool_s': median(w['foreground_first_tool_s'] for w in waves),
                'median_foreground_checked_s': median(w['foreground_checked_s'] for w in waves)}
    with (root / 'results/hermes-fleet-waves.csv').open() as f:
        csvrows = list(csv.DictReader(f))
    assert len(csvrows) == 15
    for row, wave in zip(csvrows, payload['hermes_fleet']):
        assert row['strategy'] == wave['strategy'] and int(row['block']) == wave['block']
        for key in ('active_worker_limit', 'checked_workers'):
            assert int(row[key]) == wave[key]
        for key in ('worker_wave_s', 'foreground_first_tool_s', 'foreground_checked_s'):
            close(float(row[key]), wave[key])
        close(float(row['checked_tasks_per_active_hour']), 3600 * wave['checked_workers'] / wave['worker_wave_s'])
        rr = [c for a in wave['sessions'] for c in a['calls']]
        rate = sum(c['native_output_tokens'] for c in rr) / (
            max(c['ended_s'] for c in rr) - min(c['started_s'] for c in rr))
        close(float(row['native_output_tok_s']), rate)
    assert len(payload['resumes']) == 4
    with (root / 'results/hermes-context-resume.csv').open() as f:
        csvrows = list(csv.DictReader(f))
    assert len(csvrows) == 4
    for row, attempt in zip(csvrows, payload['resumes']):
        for key, value in attempt.items():
            if isinstance(value, str):
                assert row[key] == value
            elif isinstance(value, bool):
                assert row[key] == str(value)
            else:
                close(float(row[key]), value)
    for policy in ('stable', 'rotate'):
        rows = [r for r in payload['resumes'] if r['cache'] == policy]
        assert len(rows) == 2
        for r in rows:
            assert r['success'] and r['resume'] and r['observed_idle_s'] >= 20
            assert r['first_prompt_cached_tokens'] == 0
            assert r['resumed_cached_tokens'] == (5120 if policy == 'stable' else 0)
        result['context_resume'][policy] = {
            'attempts': len(rows), 'prompt_tokens': [r['resumed_prompt_tokens'] for r in rows],
            'cached_tokens': [r['resumed_cached_tokens'] for r in rows],
            'median_first_tool_s': median(r['resume_first_tool_s'] for r in rows),
            'median_checked_s': median(r['resume_checked_s'] for r in rows)}
    result['counts'] = {'c8_timed_waves': 120, 'c8_timed_responses': 960,
                        'c16_timed_waves': 80, 'c16_timed_responses': 1280,
                        'pilot_background_passed': 48, 'pilot_foreground_passed': 6,
                        'fleet_background_passed': 240, 'fleet_foreground_passed': 15,
                        'resume_attempts_passed': 4, 'fleet_model_streams': calls['hermes_fleet']}
    assert calls['hermes_pilot'] == 162 and calls['hermes_fleet'] == 765
    return result


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--write-summary', action='store_true')
    args = cli.parse_args()
    data = verify()
    path = ROOT / 'results/vllm-followup-summary.json'
    if args.write_summary:
        path.write_text(json.dumps(data, indent=2) + '\n')
    else:
        assert data == json.loads(path.read_text()), 'committed summary differs from observations'
    print(json.dumps(data, indent=2))
