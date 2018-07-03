"""
    XCOM1/2 custom file format parsers.

    By definition has nothing to do with SDL or other libs.

    Loader functions return raw data only.
"""

import struct, pprint ,io
import collections, copy
from recordclass import recordclass

def load_world_dat(planet_dat):
    "http://www.ufopaedia.org/index.php/WORLD.DAT"
    dat = open(planet_dat, "rb").read()
    dat_t = struct.Struct('<hhhhhhhhhh')
    rv = []
    # 8
    for rec in struct.iter_unpack('<hhhhhhhhhh', dat):
        if rec[6] == -1: # tri
            rv.append([rec[8]] + list(map(lambda x: x/8.0, rec[:6])))
        else: # quad
            rv.append([rec[8]] + list(map(lambda x: x/8.0, rec[:8])))
    return rv

def load_palette(ruleset, palname):
    " http://www.ufopaedia.org/index.php/PALETTES.DAT "
    pmeta = ruleset['_palettes'][palname]
    rgb_t = struct.Struct('BBB')
    paldata = open(pmeta['file'], 'rb').read()[pmeta['offs']:pmeta['offs']+pmeta['size']]

    pal = []
    iu = rgb_t.iter_unpack(paldata)
    for r, g, b in iu:
        pal.append((r<<2, g<<2, b<<2, 255))
    return pal

def load_all_pallettes(ruleset):
    return dict((palname, load_palette(ruleset, palname)) for palname in ruleset['_palettes'].keys())

def save_palette_txt(pal, fname):
    with open(fname, "w") as f:
        f.write("{:d}\n".format(len(pal)))
        for entry in pal:
            f.write("{:d},{:d},{:d}\n".format(*pal))

def decode_spk(data):
    """ https://www.ufopaedia.org/index.php/Image_Formats#SPK """
    ret_data = bytearray(320*200)
    posn = 0
    with io.BytesIO(data) as f:
        def get():
            return struct.unpack("<H", f.read(2))[0]
        while True:
            a = get()
            if a == 0xFFFF:
                skip = get()*2
                posn += skip
            elif a == 0xFFFE:
                count = get()*2
                ret_data[posn:posn+count] = f.read(count)
                posn += count
            elif a == 0xFFFD:
                break
    return ret_data


def decode_bdy(data):
    """ https://www.ufopaedia.org/index.php/Image_Formats#BDY """
    ret_data = bytearray(320*200)
    posn = 0
    rownum = 0
    with io.BytesIO(data) as f:
        pass
    return ret_data

def get_sprite_mergelist(ruleset, typestr):
    "bruteforce a mergelist wrt all mods there"
    ml = []
    for sd in ruleset['extraSprites']:
        if sd['type'].lower() == typestr.lower():
            ml.append(sd)
    ml.sort(key = lambda x: x['_mod_index'])
    return ml

def load_texture_dat(texture_dat, subX, subY):
    """http://www.ufopaedia.org/index.php/TEXTURE.DAT

    this returns a list of 32x32x1 byte objects,
    """
    lodlevels = 3
    reclen = subX * subY
    data = open(texture_dat, 'rb').read()
    tex_in_lod = (len(data)//reclen)//lodlevels

    rv = []
    i = 0
    for lod in range(lodlevels):
        for texi in range(tex_in_lod):
            rv.append(data[i*reclen:(i+1)*reclen])
            i += 1
    return rv

def load_and_slice_textures(imgfname, subX, subY, surf_load, surf_cut):
    """ loads an image with surf_load and slices it into textures
        with surf_cut
    """
    surf = surf_load(imgfname)
    w = surf.contents.w
    h = surf.contents.h
    rv = []
    for iy in range(int(h/subY)):
        for ix in range(int(w/subX)):
           rv.append(surf_cut(surf, ix*subX, iy*subY, subX, subY))
    return rv

def load_geotextures(ruleset, surf_conv, surf_load, surf_cut):
    """ returns patched flat list of suitable converted/loaded surfaces
        surf_conv should accept (bytes, w, h, pal)
        surf_load should accept a filename

        to be expanded so that a texalbum builder is accepted instead.
    """
    ml = get_sprite_mergelist(ruleset, 'texture.dat')
    tdat = ml.pop(0)
    if len(tdat['files']) != 1 or 'subX' not in tdat:
        raise BadMod("first texture.dat has no subX")

    pal = load_palette(ruleset, 'PAL_GEOSCAPE')
    tbyteseqs = load_texture_dat(tdat['files'][0], tdat['subX'], tdat['subY'])
    print("loaded", tdat['files'][0])
    rv = []
    for tbyteseq in tbyteseqs:
        rv.append(surf_conv(tbyteseq, tdat['subX'], tdat['subY'], pal))

    """ okay, tpatch can be either:
        - lack subX, contain multiple files with indices (piratez)
        - have subX, contain a file that replaces all  (hobbes), with lodlevels and such?
    """
    for tpatch in ml:
        pprint.pprint(ml)
        if len(tpatch['files']) == 1 and 'subX' in tpatch:
            pprint.pprint(tpatch)
            rv = load_and_slice_textures(tpatch['files'][0], tpatch['subX'], tpatch['subY'], surf_load, surf_cut)
        else:
            for tidx, tname in tpatch['files'].items():
                print(tidx, tname)
                rv[tidx] = surf_load(tname)

    return rv

def load_pck(pck_path, tab_path, tab_type = 2, w = 32):
    if tab_type == 2:
        tab_type = struct.Struct("<H")
    elif tab_type == 4:
        tab_type = struct.Struct("<I")
    if tab_path is not None:
        tab_data = list(tab_type.iter_unpack(open(tab_path, 'rb').read()))
    else:
        tab_data = [0]
    rv = []
    pck_data = open(pck_path, 'rb').read()
    tab_data.append(len(pck_data))
    for pck_start, pck_end in zip(tab_data[::2], tab_data[1::2]):
        rle_data = pck_data[pck_start:pck_end]
        raw_data = bytearray(w * rle_data[0])
        rle_idx = 1
        while rle_idx < len(rle_data):
            rbyte = rle_data[rle_idx]
            if rbyte == 0xFF:
                # maybe fill out the rest of raw_data?
                break
            elif rbyte == 0xFE:
                raw_data += bytes(rle_data[rle_idx+1])
                rle_idx += 1
            else:
                raw_data.append(rbyte)
            rle_idx += 1
        rv.append(raw_data)
    return rv

MapRec = collections.namedtuple('MapRec', 'floor west north ob')
MapStruct = collections.namedtuple('MapStruct', 'cells height width depth')
def load_map(map_path):
    map_data = open(map_path, 'rb').read()
    eb = (len(map_data) - 3) % 4
    if eb > 0:
        #print("{}: {} extra bytes".format(map_path, eb))
        # many maps seem to have an extra byte tacked on.
        # must be a bug in some editor
        pass
    return MapStruct(
        [MapRec(*rec) for rec in struct.iter_unpack('4B', map_data[3:-eb])],
        *struct.unpack('3B', map_data[:3]))

MCDRec = recordclass('MCDRec', '''origin Frame LOFT ScanG UFO_Door
        Stop_LOS No_Floor Big_Wall Gravlift Door Block_Fire Block_Smoke
        u39 TU_Walk TU_Slide TU_Fly Armor HE_Block Die_MCD Flammable Alt_MCD
        u48 T_Level P_Level u51 Light_Block Footstep Tile_Type HE_Type
        HE_Strength Smoke_Blockage Fuel Light_Source Target_Type Xcom_Base u62''')

MCDStruct = struct.Struct("<8s12sH8x12B6Bb13B")
MCDPatchMap = {
    'bigWall': 'Big_Wall',
    'TUWalk': 'TU_Walk',
    'TUSlide': 'TU_Slide',
    'TUFly': 'TU_Fly',
    'deathTile': 'Die_MCD',
    'terrainHeight': 'T_Level',
    'specialType': 'Target_Type',
    'explosive': 'HE_Strength',
    'armor': 'Armor',
    'flammability': 'Flammable',
    'fuel': 'Fuel',
    'footstepSound': 'Footstep',
    'HEBlock': 'HE_Block',
    'noFloor': 'No_Floor',
    'LOFTS': 'LOFT',
    'stopLOS': 'Stop_LOS',
    'objectType': 'Tile_Type',
}
def load_mcd(mcd_path, mcd_patch, mcd_offset):
    mcdp = {}
    if mcd_patch is not None:
        for p in mcd_patch:
            cp = copy.copy(p)
            del cp['MCDIndex']
            mcdp[p['MCDIndex']] = dict(((MCDPatchMap[k], v) for k, v in cp.items()))
    mcdi = 0
    rv = []
    for mcd in (MCDRec(None, *i) for i in MCDStruct.iter_unpack(open(mcd_path, 'rb').read())):
        mcd.Frame = struct.unpack("8B", mcd.Frame)
        mcd.LOFT = struct.unpack("12B", mcd.LOFT)
        mcd.origin = "{}:{}".format(mcd_path, mcdi)
        if mcdi in mcdp:
            mcd = mcd._replace(**mcdp[mcdi])
        mcdi +=1
        rv.append(mcd)
    return rv

class RouteRec(object):
    def __init__(self, data):
        self.y, self.x, self.z = struct.unpack('BBB', data[:3])
        self.type, self.rank, self.flags, self.reserved, self.priority = struct.unpack('BBB', data[-5:])
        self.links = list(struct.iter_unpack('BBB', data[3:-5]))

def load_rmp(rmp_path):
    rmp_data = open(rmp_path, 'rb').read()
    rv = []
    for i in range(len(rmp_data)/24):
        rv.append(RouteRec(rmp_data[i*24:(i+1)*24-1]))
    return rv

