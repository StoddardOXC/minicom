#!/usr/bin/env python3

"""
Reads latest (arg: user/piratez) or designated (arg: user/piratez/whatever.sav) save game

  - In battlescape mode shows units' coordinates and vital stats
    (health, stun, wounds, armor if appicable, morale and willingness to surrender)
  - In geoscape mode 'fgrep -i' -s through inventory across all bases and craft
    (substring arg required, case insensetive)

To be run from the game's top dir of a standalone install under Linux.

"""

import math, pprint, sys, os, copy, fnmatch, pprint, time, re, argparse
import yaml

FALLBACK_LANG = 'en-US'

def yamload(path):
    return yaml.load_all(open(path, "rb"), Loader = yaml.CLoader)

def merge_lang(lang, path):
    rul_es = list(yamload(path))[0]
    if 'en-US' in rul_es:
        lang.update(rul_es['en-US'])
    else:
        for strset in rul_es.get('extraStrings', {}):
            if strset['type'] == 'en-US':
                lang.update(strset['strings'])

lang = {}
merge_lang(lang, 'common/Language/en-US.yml')
merge_lang(lang, 'standard/xcom1/Language/en-US.yml')
merge_lang(lang, 'user/mods/Piratez/Language/en-US.yml')


if os.path.isdir(sys.argv[1]):
    lmt = 0
    sel = None
    for fname in os.listdir(sys.argv[1]):
        fname = os.path.join(sys.argv[1], fname)
        if not os.path.isdir(fname) and fname.endswith(('.asav', '.sav')):
            mt = os.stat(fname).st_mtime
            if mt > lmt:
                lmt = mt
                sel = fname
    fname = sel
else:
    fname = sys.argv[1]
print("Reading", fname, "\n")

doc = list(yamload(fname))[1]

soldiers = {}
for base in doc['bases']:
    for soldier in base.get('soldiers', []):
        soldiers[soldier['id']] = soldier

if 'battleGame' in doc:
    for unit in doc['battleGame']['units']:
        fwc = sum(unit['fatalWounds'])
        if unit['id'] >= 1000000:
            if unit['health'] > 0:
                ds = unit['stunlevel'] - unit['health']
                if unit['stunlevel'] > 0:
                    dss = "stun {}".format(ds)
                else:
                    dss = ""

                doa = "dead in {}".format(unit['health'] // fwc) if fwc > 0 else ''
                utype = lang.get(unit['genUnitType'], unit['genUnitType'])
                wts = 'SHITHEAD [m:{}]'.format(unit['morale']) if (
                    not unit['wantsToSurrender']
                    and not dss and unit['faction'] == 1) else ''

                print(unit['faction'],
                        "[{: >2d}, {: >2d}, {: >2d}]".format(*unit['position']),
                        "{:20s}{: >3d}{: >4d}{: >3d}".format(utype,
                            unit['health'],
                            unit['stunlevel'], fwc),
                        "[{: >3d}, {: >3d}, {: >3d}, {: >3d}, {: >3d}]".format(*unit['armor']),
                        dss, wts, doa)
        else:
            print(unit['faction'],
                   "[{: >2d}, {: >2d}, {: >2d}] {:20s}{: >3d}{: >4d}{: >3d}".format(*unit['position'],
                    soldiers[unit['id']]['name'], unit['health'], unit['stunlevel'], fwc))

elif len(sys.argv) > 2:
    pattern = ' '.join(sys.argv[2:])
    def match(s):
        rr = re.search(pattern, s, re.IGNORECASE)
        return rr is not None
    totals = {}
    def tinc(name, amt):
        try:
            totals[name] += amt
        except KeyError:
            totals[name] = amt
    for base in doc['bases']:
        total_space = 0
        used_space = 0
        act_amt = 0
        inc_amt = 0
        for item,amt in base.get('items', {}).items():
            unit_vol = 42
            used_space += amt * unit_vol
        print(base['name'])
        for item,amt in base.get('items', {}).items():
            if match(lang.get(item, item)):
                print("    ", lang[item], amt)
                tinc(lang[item], amt)
        for craft in base.get('crafts', []):
            cname = craft.get('name', lang[craft['type']])
            for item,amt in craft.get('items', {}).items():
                if match(lang.get(item, item)):
                    print("    ", lang[item], amt, " in ", cname)
                    tinc(lang[item], amt)
            for weap in craft.get('weapons', []):
                if weap['type'] == 0:
                    continue
                if match(lang.get(weap['type'], weap['type'])):
                    print("    ", lang[weap['type']], weap['ammo'], " in ", cname)
        for trans in base.get('transfers', []):
            if 'soldier' in trans or 'craft' in trans:
                continue
            try:
                if match(lang[trans['itemId']]):
                    print("  ", '+', lang[trans['itemId']], trans['itemQty'])
                    tinc(lang[trans['itemId']], trans['itemQty'])
            except:
                print(trans)
    print("\nTotal:")
    for name, amt in totals.items():
        print(name, amt)

