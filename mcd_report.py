#!/usr/bin/env python3

import sys, time
from modloader import load_ruleset, list_to_dict
import fileformats

import pprint

class WTF(Exception):
    pass

allmcds = {}

def load_mapdataset(mapdatafiles, mcdpatches):
    offset = 0
    rv = []
    for md in mapdatafiles:
        if md['mcd'] is None:
            raise WTF
        patch = mcdpatches.get(md['type'], {'data':None})['data']
        mcds = fileformats.load_mcd(md['mcd'], patch, offset)
        rv.extend(mcds)
        offset += len(mcds)
        allmcds[md['mcd']] = len(mcds)
    return rv

def missing_mdfs(terrain):
    for mdf in terrain['mapDataFiles']:
        m = ''
        if mdf['mcd'] is None:
            m += 'mcd '
        if mdf['pck'] is None:
            m += 'pck '
        if mdf['tab'] is None:
            m += 'tab'
        if len(m):
            print("{}: {} is missing {}".format(terrain['name'], mdf['type'], m))

def main():
    st = time.time()
    ruleset = load_ruleset(sys.argv[1])
    print("Ruleset loaded in {:.1f} s".format(time.time() - st))

    mcdpatches = list_to_dict('type', ruleset["MCDPatches"])
    #pprint.pprint(mcdpatches)

    for terrain in ruleset["terrains"]:
        try:
            mds = load_mapdataset(terrain['mapDataFiles'], mcdpatches)
        except WTF:
            missing_mdfs(terrain)
            continue
        for mfs in terrain["mapFiles"]:
            i = 0
            if mfs["map"] is None:
                print("{}: {}.MAP is missing.".format(terrain['name'], mfs['type']))
                continue
            map = fileformats.load_map(mfs["map"])
            for cell in map.cells:
                z = i // (map.width * map.height)
                y = (i - z * (map.width * map.height)) // map.width
                x = (i - z * (map.width * map.height) - y * map.width)
                z = map.depth - z -1
                mcd = mds[cell.floor]
                if mcd.TU_Walk == 0:
                    print("{} {} ({},{},{}) mcdidx={}: {}".format(terrain['name'], mfs["map"], x, y, z, cell.floor, mcd))
                i += 1
    ems = 0
    for mcd, c in allmcds.items():
        ems += c
    print("Total: {} mcdefs".format(ems))

if __name__ == '__main__':
    main()

