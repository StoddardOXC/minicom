#!/usr/bin/env python3

"""
Reads latest (arg: user/piratez) or designated (arg: user/piratez/whatever.sav) save game

  - In battlescape mode shows units' coordinates and vital stats
    (health, stun, wounds, armor if appicable, morale and willingness to surrender)
  - In geoscape mode 'fgrep -i' -s through inventory across all bases and craft
    (substring arg required, case insensitive)

To be run from the game's top dir of a standalone install under Linux.

"""

# well this is fucked up
def acolor(i, s):
    if i in range(8):
        clr = 30 + i
    elif i in range (8,16):
        clr = 90 + i
    else:
        return ""
    return '\033[{}m{}\033[0m'.format(clr,s)

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

fwmap = {
    'F': 'Ƒ',
    'f': 'ƒ',
    'E': 'Ё',
    'e': 'ё',
    'C': 'Č',
    'c': 'č',
    'T': 'Ť',
    't': 'ť',
}
SHC = 3+8 # shithead red bg

if 'battleGame' in doc:
    try:
        lvl = int(sys.argv[2])
    except:
        lvl = None

    unitrep = []
    unitpos = {}
    shithead_count = 0
    shitheads_at_level = 0
    for unit in doc['battleGame']['units']:
        at_level = lvl is None or unit['position'][2] == lvl # at selected level if any
        fwc = sum(unit['fatalWounds'])
        u_type = lang.get(unit['genUnitType'], unit['genUnitType'])
        u_name = soldiers.get(unit['id'],{'name': u_type})['name']
        doa = "dead in {}".format(unit['health'] // fwc) if fwc > 0 else ''
        ds = unit['stunlevel'] - unit['health']

        u_state = ' '
        u_type = ('F',
            'T' if 'TERRORIST' in unit['genUnitType'] else 'E',
            'C')[unit['faction']] # fuck off with enum values in yaml for god's sake.

        if ds >= 0:
            dss = "STUN {: >3d}".format(ds)
            u_type = u_type.lower()
            u_state = 's'
        elif unit['stunlevel'] == 0:
            dss = "        "
        else:
            dss = "stun {: >3d}".format(ds)

        armor = "[{: >3d}, {: >3d}, {: >3d}, {: >3d}, {: >3d}]".format(*unit['armor'])

        if unit['status'] == 6: # fucking STATUS_DEAD shit never put enum values into yaml
            u_type = u_type.lower()
            u_state = 'd'
        else:
            if fwc > 0:
                u_type = fwmap[u_type]

            ur = " ".join(map(str, (unit['faction'],
                       "[{: >2d}, {: >2d}, {: >2d}] {: >3d} {:20s} {: >3d} st:{: >4d} fw:{: >3d} m:{: >3d}".format(
                            *unit['position'], unit['tu'],
                            u_name,
                            unit['health'], unit['stunlevel'], fwc, unit['morale']),
                            armor, '')))
            wts = '        '
            if unit['faction'] == 0:
                pass
            elif unit['faction'] == 1:
                if not unit['wantsToSurrender']:
                    wts = 'SHITHEAD'
                    shithead_count += 1
                    if at_level:
                        shitheads_at_level += 1
                    u_type = acolor(SHC, u_type)
                ur += " ".join((dss, doa, wts))
            else:
                ur += " ".join((dss, doa))
            if at_level:
                unitrep.append(ur)
        if at_level:
            if u_state == ' ':
                u_state = str(unit['position'][2])
            unitpos[(unit['position'][0], unit['position'][1])] = u_type + u_state

    l = "   "
    for x in range(0, doc['battleGame']['width']):
        l += "{: >2d}".format(x % 10) if x % 10 else '  '
    print(l)
    for y in range(0, doc['battleGame']['length']):
        l = "{:02}: ".format(y)
        for x in range(0, doc['battleGame']['width']):
            if (x,y) in unitpos:
                l += str(unitpos[(x,y)])
            else:
                l += '. ' if y % 10 and x % 10 else ': '
        print(l)
    print("\nShithead count: {}/{}".format(shitheads_at_level, shithead_count))
    print("\n".join(unitrep))

elif len(sys.argv) > 2:
    patterns = ' '.join(sys.argv[2:]).split(',')
    print(repr(patterns))
    def match(s, v = False):
        for pattern in patterns:
            rr = re.search(pattern, s, re.IGNORECASE)
            if rr is not None:
                if v:
                    print("match(): {} {}".format(pattern, s))
                return True
        return False
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
        report = [base['name']]
        for craft in base.get('crafts', []):
            cr_rep = ["    " + craft.get('name', lang[craft['type']])]
            for item, amt in craft.get('items', {}).items():
                if match(lang.get(item, item)):
                    cr_rep.append("{}{} {}".format(" " * 8, lang.get(item, item), amt))
                    tinc(lang[item], amt)
            for weap in craft.get('weapons', []):
                if weap['type'] == 0:
                    continue
                if match(lang.get(weap['type'], weap['type'])):
                    cr_rep.append("{}{} {}".format(" " * 8, lang[weap['type']], weap['ammo']))
            if len(cr_rep) > 1:
                report.extend(cr_rep)
        for item,amt in base.get('items', {}).items():
            if match(lang.get(item, item)):
                report.append("{}{} {}".format(" " * 4, lang.get(item, item), amt))
                tinc(lang.get(item, item), amt)
        armors = {}
        for unit in base.get('soldiers', []):
            armor = lang.get(unit['armor'], unit['armor'])
            if match(armor):
                try:
                    armors[armor] += 1
                except:
                    armors[armor] = 1
        for armor, amt in armors.items():
            report.append("{} equipped {} {}".format(" " * 4, armor, amt))
            tinc(armor, amt)
        for trans in base.get('transfers', []):
            if 'soldier' in trans or 'craft' in trans:
                continue
            try:
                if match(lang[trans['itemId']]):
                    report.append("{} + {} {}".format(" " * 1, lang[trans['itemId']], trans['itemQty']))
                    tinc(lang[trans['itemId']], trans['itemQty'])
            except:
                print(trans)
        if len(report) > 1:
            print("\n".join(report), "\n")
    print("Totals:")
    if len(totals) == 0:
        print(" " * 4, None)
    for name, amt in totals.items():
        print(" " * 4, name, amt)

