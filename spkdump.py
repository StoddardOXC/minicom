#!/usr/bin/env python3

#
# requires pip3 install recordclass PySDL2
# and https://github.com/lxnt/SDL_pnglite for writing indexed-color pngs
#
#

import math, pickle, pprint, sys, os, collections, time
import render2d
from render2d import bufpal2surface, bufpal2palsurf, file2surface, chunkofsurface
import fileformats

from ctypes import POINTER, c_int, c_char_p
from sdl2 import SDL_Surface, SDL_RWops
import sdl2.dll
import sdl2.rwops

pnglite = sdl2.dll.DLL("SDL_pnglite", ["SDL_pnglite"], os.getenv("PYSDL2_DLL_PATH"))
SDL_LoadPNG_RW = pnglite.bind_function("SDL_LoadPNG_RW", [POINTER(SDL_RWops), c_int, c_char_p], POINTER(SDL_Surface))
SDL_SavePNG_RW = pnglite.bind_function("SDL_SavePNG_RW", [POINTER(SDL_Surface), POINTER(SDL_RWops), c_int], c_int)

def save_png(surf, fname):
    fobj = open(fname, "wb")
    rwops = sdl2.rw_from_object(fobj)
    SDL_SavePNG_RW(surf, rwops, 0)
    sdl2.SDL_RWclose(rwops)
    fobj.close()

import ruleset
tr = ruleset.get_trans(fallback=True)
rs = ruleset.ruleset

render2d.init()

palettes = fileformats.load_all_pallettes(rs)
palettes[''] = palettes['PAL_GEOSCAPE']

PLOOKUP = {
    'back01.scr': 'PAL_GEOSCAPE',
    'back02.scr': 'PAL_GEOSCAPE',
    'back03.scr': 'PAL_GEOSCAPE',
    'back04.scr': 'PAL_GEOSCAPE',
    'back05.scr': 'PAL_GEOSCAPE',
    'back06.scr': 'PAL_GEOSCAPE',
    'back07.scr': 'PAL_GEOSCAPE',
    'back08.scr': 'PAL_GEOSCAPE',
    'back09.scr': 'PAL_GEOSCAPE',
    'back10.scr': 'PAL_GEOSCAPE',
    'back11.scr': 'PAL_GEOSCAPE',
    'back12.scr': 'PAL_GEOSCAPE',
    'back13.scr': 'PAL_GEOSCAPE',
    'back14.scr': 'PAL_GEOSCAPE',
    'back15.scr': 'PAL_GEOSCAPE',
    'back16.scr': 'PAL_GEOSCAPE',
    'back17.scr': 'PAL_GEOSCAPE',
    'detbord2.pck': 'PAL_BATTLESCAPE',
    'detbord.pck': 'PAL_BATTLESCAPE',
    'geobord.scr': 'PAL_GEOSCAPE',
    'graphs.spk': 'PAL_GRAPHS',
    'icons.pck': 'PAL_BATTLESCAPE',
    'man_0f0.spk': 'PAL_BATTLEPEDIA',
    'man_0f1.spk': 'PAL_BATTLEPEDIA',
    'man_0f2.spk': 'PAL_BATTLEPEDIA',
    'man_0f3.spk': 'PAL_BATTLEPEDIA',
    'man_0m0.spk': 'PAL_BATTLEPEDIA',
    'man_0m1.spk': 'PAL_BATTLEPEDIA',
    'man_0m2.spk': 'PAL_BATTLEPEDIA',
    'man_0m3.spk': 'PAL_BATTLEPEDIA',
    'man_1f0.spk': 'PAL_BATTLEPEDIA',
    'man_1f1.spk': 'PAL_BATTLEPEDIA',
    'man_1f2.spk': 'PAL_BATTLEPEDIA',
    'man_1f3.spk': 'PAL_BATTLEPEDIA',
    'man_1m0.spk': 'PAL_BATTLEPEDIA',
    'man_1m1.spk': 'PAL_BATTLEPEDIA',
    'man_1m2.spk': 'PAL_BATTLEPEDIA',
    'man_1m3.spk': 'PAL_BATTLEPEDIA',
    'man_2.spk': 'PAL_BATTLEPEDIA',
    'man_3.spk': 'PAL_BATTLEPEDIA',
    'medibord.pck': 'PAL_BATTLESCAPE',
    'scanbord.pck': 'PAL_BATTLESCAPE',
    'tac01.scr': 'PAL_BATTLEPEDIA',
    'unibord.pck': '',
    'up001.spk': 'PAL_UFOPAEDIA',
    'up002.spk': 'PAL_UFOPAEDIA',
    'up003.spk': 'PAL_UFOPAEDIA',
    'up004.spk': 'PAL_UFOPAEDIA',
    'up005.spk': 'PAL_UFOPAEDIA',
    'up006.spk': 'PAL_BATTLEPEDIA',
    'up007.spk': 'PAL_BATTLEPEDIA',
    'up008.spk': 'PAL_BATTLEPEDIA',
    'up009.spk': 'PAL_BATTLEPEDIA',
    'up010.spk': 'PAL_BATTLEPEDIA',
    'up011.spk': 'PAL_BATTLEPEDIA',
    'up012.spk': 'PAL_UFOPAEDIA',
    'up013.spk': 'PAL_UFOPAEDIA',
    'up014.spk': 'PAL_UFOPAEDIA',
    'up015.spk': 'PAL_UFOPAEDIA',
    'up016.spk': 'PAL_UFOPAEDIA',
    'up017.spk': 'PAL_UFOPAEDIA',
    'up018.spk': 'PAL_UFOPAEDIA',
    'up019.spk': 'PAL_UFOPAEDIA',
    'up020.spk': 'PAL_UFOPAEDIA',
    'up021.spk': 'PAL_UFOPAEDIA',
    'up022.spk': 'PAL_UFOPAEDIA',
    'up023.spk': 'PAL_UFOPAEDIA',
    'up024.spk': 'PAL_UFOPAEDIA',
    'up025.spk': 'PAL_UFOPAEDIA',
    'up026.spk': 'PAL_UFOPAEDIA',
    'up027.spk': 'PAL_UFOPAEDIA',
    'up028.spk': 'PAL_UFOPAEDIA',
    'up029.spk': 'PAL_UFOPAEDIA',
    'up030.spk': 'PAL_UFOPAEDIA',
    'up031.spk': 'PAL_UFOPAEDIA',
    'up032.spk': 'PAL_UFOPAEDIA',
    'up033.spk': 'PAL_UFOPAEDIA',
    'up034.spk': 'PAL_UFOPAEDIA',
    'up035.spk': 'PAL_UFOPAEDIA',
    'up036.spk': 'PAL_UFOPAEDIA',
    'up037.spk': 'PAL_UFOPAEDIA',
    'up038.spk': 'PAL_UFOPAEDIA',
    'up039.spk': 'PAL_UFOPAEDIA',
    'up040.spk': 'PAL_UFOPAEDIA',
    'up041.spk': 'PAL_UFOPAEDIA',
    'up042.spk': 'PAL_UFOPAEDIA',
    'up_bord1.spk': 'PAL_BATTLEPEDIA',
    'up_bord2.scr': 'PAL_BATTLEPEDIA',
    'up_bord2.spk': 'PAL_BATTLEPEDIA',
    'up_bord3.spk': 'PAL_BATTLEPEDIA',

}

for es in rs['extraSprites']:
    try:
        rtype = es['resType']
        ptype = PLOOKUP.get(es['type'], '')
        pdata = palettes[ptype]
        w, h = es['width'], es['height']
        fname = es['files'][0]
    except KeyError:
        print(es['type'])
        continue
    data = open(fname, 'rb').read()
    if rtype == 'SCR' and not fname.endswith('.dat'):
        print ("{} bytes from {} ptype={}".format(len(data), fname, ptype))
        surf = bufpal2palsurf(data, w, h, pdata)
        save_png(surf, os.path.join(sys.argv[1], es['type'] + '.' + rtype + '.png'))
    elif rtype == 'SPK':
        print ("{} bytes from {} ptype={}".format(len(data), fname, ptype))
        buf = fileformats.decode_spk(data)
        surf = bufpal2palsurf(buf, w, h, pdata)
        save_png(surf, os.path.join(sys.argv[1], es['type'] + '.' + rtype + '.png'))
    else:
        continue

