"""Спільне для online-now: запити з примусовим IPv4 і розбір сторінки t.me/<група>."""
import html
import re
import socket
import urllib.error
import urllib.request

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/141 Safari/537.36')

# IPv6 з ноутбука мертвий: urllib чекає весь тайм-аут, перш ніж узяти IPv4.
_orig_gai = socket.getaddrinfo


def _gai_v4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_gai(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _gai_v4


def get(url, timeout=20):
    """Повертає (код, текст). Код None — мережева помилка (текст тоді її опис)."""
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception as e:  # тайм-аут, DNS, обрив
        return None, f'{type(e).__name__}: {e}'


_EXTRA = re.compile(r'<div class="tgme_page_extra">\s*(.*?)\s*</div>', re.S)
_NUM = r'([\d][\d\s  ,]*)'


def _int(s):
    return int(re.sub(r'[^\d]', '', s))


def parse_tme(page):
    """Розбирає t.me/<ім'я>. Повертає dict: kind (group|channel|user|none), members, online, title, extra."""
    m = _EXTRA.search(page)
    extra = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip() if m else ''
    t = re.search(r'<meta property="og:title" content="([^"]*)"', page)
    title = html.unescape(t.group(1)) if t else ''
    out = {'kind': 'none', 'members': None, 'online': None, 'title': title, 'extra': extra}
    g = re.match(_NUM + r'\s*members?(?:,\s*' + _NUM + r'\s*online)?', extra)
    if g:
        out.update(kind='group', members=_int(g.group(1)),
                   online=_int(g.group(2)) if g.group(2) else 0)
    elif re.match(_NUM + r'\s*subscribers?', extra):
        out['kind'] = 'channel'
    elif extra.startswith('@'):
        out['kind'] = 'user'
    return out
