#!/usr/bin/env python3
"""Grade a batch plugin benchmark output JSON.

Usage: grade_batch.py <output.json> <domain> <n_questions>

Returns: n_correct/n_total
"""
import json
import sys

out_path, domain, n = sys.argv[1], sys.argv[2], int(sys.argv[3])

tasks_path = __file__.replace('/scale/grade_batch.py', '/plugin_tasks.json')
with open(tasks_path) as f:
    tasks = json.load(f)['tasks'][domain][:n]

with open(out_path) as f:
    data = json.load(f)

text = (data.get('result') or '').lower()
correct = sum(1 for t in tasks if t['answer_token'].lower() in text)

print(f'{correct}/{n}')
if correct < n:
    missing = [t['answer_token'] for t in tasks if t['answer_token'].lower() not in text]
    print(f'Missing: {missing}', file=sys.stderr)
