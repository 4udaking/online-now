"""Один слот online-now: знімає «N members, M online» зі сторінок t.me/<група> для панелі груп.

Запускається GitHub Actions раз на 15 хв (workflow_dispatch від зовнішнього будильника,
cron як запасний). Слот — поточна чверть години UTC. Якщо файл слоту вже є, виходить
(cron і будильник не дублюють одне одного). Слот, що почався понад 10 хв тому, пропускає.

Запити йдуть послідовно й рівномірно до slot+13 хв. Сплеск t.me карає заглушкою з кодом 200:
сторінка без назви й лічильників. Таку відповідь записуємо як «stub» (не виміряно).
Канарка на початку відрізняє обмеження від зниклої групи.

Сирі рядки шифруються відкритим ключем (cert.pem, CMS/AES-256) — розшифрувати може
лише власник закритого ключа. Відкрито лежить тільки health.ndjson: лічильники ok/stub,
без значень online.
"""
import gzip
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lib import get, parse_tme

HERE = Path(__file__).resolve().parent
SLOT = 900
FINISH_BY = 780          # усі запити — до slot + 13 хв
LATE_LIMIT = 600         # слот, що почався понад 10 хв тому, не беремо
MIN_STEP = 1.5           # не частіше за запит на 1,5 с
CANARY = 'python_ru'


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def measure(user):
    code, page = get(f'https://t.me/{user}')
    if code != 200:
        return {'s': f'http{code}' if code else 'err'}
    r = parse_tme(page)
    if r['kind'] == 'group':
        return {'s': 'ok', 'm': r['members'], 'o': r['online']}
    if r['kind'] == 'none' and not r['title']:
        return {'s': 'stub'}
    return {'s': r['kind']}


def health(row):
    with open(HERE / 'data' / 'health.ndjson', 'a') as f:
        f.write(json.dumps(row) + '\n')


def main():
    t0 = time.time()
    slot = t0 // SLOT * SLOT
    day, hhmm = iso(slot)[:10], iso(slot)[11:16].replace(':', '')
    out = HERE / 'data' / day / f'{hhmm}.ndjson.gz.p7m'
    base = {'slot': iso(slot), 'start': iso(t0), 'run': os.environ.get('GITHUB_RUN_ID'),
            'event': os.environ.get('GITHUB_EVENT_NAME')}
    if out.exists():
        print(f'слот {iso(slot)} уже записаний — виходжу')
        return
    if t0 - slot > LATE_LIMIT:
        print(f'слот {iso(slot)} почався {round(t0 - slot)} с тому — пропускаю')
        health({**base, 'skipped': 'late', 'late': round(t0 - slot)})
        return

    groups = json.loads((HERE / 'lists' / 'panel.json').read_text())['groups']
    # Порядок перемішаний раз і назавжди (той самий, що в локальному збирачі).
    random.Random(20261016).shuffle(groups)

    c = measure(CANARY)
    if c['s'] != 'ok':
        print(f'канарка {c["s"]} — t.me обмежує, слот пропущено')
        health({**base, 'canary': c['s'], 'aborted': True, 'end': iso(time.time())})
        return

    step = max(MIN_STEP, (slot + FINISH_BY - time.time()) / len(groups))
    rows, cnt, streak, aborted = [], {'ok': 0, 'stub': 0, 'other': 0}, 0, False
    for i, g in enumerate(groups):
        target = t0 + 2 + i * step
        while time.time() < target:
            time.sleep(min(20, target - time.time()))
        r = measure(g['user'])
        rows.append({'t': iso(time.time()), 'slot': iso(slot), 'p': g['panel'], 'u': g['user'], **r})
        if r['s'] == 'ok':
            cnt['ok'] += 1
            streak = 0
        elif r['s'] == 'stub':
            cnt['stub'] += 1
            streak += 1
        else:
            cnt['other'] += 1
        if streak >= 5:
            if measure(CANARY)['s'] != 'ok':
                aborted = True
                print(f'5 заглушок поспіль і канарка не відповідає — обрив на {i + 1}/{len(groups)}')
                break
            streak = 0

    out.parent.mkdir(parents=True, exist_ok=True)
    raw = gzip.compress(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows).encode())
    enc = subprocess.run(['openssl', 'cms', '-encrypt', '-binary', '-aes256', '-outform', 'DER',
                          str(HERE / 'cert.pem')], input=raw, capture_output=True)
    if enc.returncode != 0:
        sys.exit('шифрування впало: ' + enc.stderr.decode()[:300])
    out.write_bytes(enc.stdout)
    health({**base, 'canary': 'ok', **cnt, 'n': len(groups), 'aborted': aborted, 'end': iso(time.time())})
    print(f'слот {iso(slot)}: {cnt}, обрив {aborted}, {round(time.time() - t0)} с → {out.relative_to(HERE)}')


if __name__ == '__main__':
    main()
