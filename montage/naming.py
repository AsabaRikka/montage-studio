"""Local labels and stable, Windows-safe output names; no media identity changes."""
import re
from datetime import datetime

RULES = [('B名称_A描述（默认）', 'b_a'), ('A描述日期_B名称', 'a_date_b'), ('前贴自定义名称_B名称', 'custom_b')]
MEDIA_EXT = re.compile(r'\.(mp4|mov|mkv|avi|webm|m4v)$', re.I)


def description(asset):
    return str(asset.get('cloud', {}).get('name') or MEDIA_EXT.sub('', asset['name'])).strip()


def display_name(asset):
    return asset.get('custom_name') or description(asset)


def clean(text):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text).strip(' .')[:72].rstrip(' .') or 'video'
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?', text, re.I):
        text = '_' + text
    return text


def output_names(assets, pairs, rule, date=None):
    if rule not in {value for _, value in RULES}:
        raise ValueError('未知命名规则，请重新选择。')
    date = date or datetime.now().strftime('%m.%d')
    used, counters, result = set(), {}, []
    for a, b in pairs:
        intro, main = assets[a], assets[b]
        aname, bname = clean(description(intro)), clean(MEDIA_EXT.sub('', main['name']))
        stem = {'b_a': f'{bname}_{aname}', 'a_date_b': f'{aname}{date}_{bname}',
                'custom_b': f'{clean(display_name(intro))}_{bname}'}[rule]
        key = stem.casefold(); number = counters.get(key, 1); candidate = stem
        while candidate.casefold() in used:
            number += 1; candidate = f'{stem}_{number}'
        counters[key] = number; used.add(candidate.casefold()); result.append(candidate + '.mp4')
    return result
