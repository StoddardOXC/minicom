"""
    XCOM1 custom file format loaders.

"""

import struct

def load_world_dat(planet_dat):
    "http://www.ufopaedia.org/index.php/WORLD.DAT"
    dat = open(planet_dat, "rb").read()
    dat_t = struct.Struct('<hhhhhhhhhh')
    rv = []
    for rec in struct.iter_unpack('<hhhhhhhhhh', dat):
        if rec[6] == -1: # tri
            rv.append([rec[8]] + list(map(lambda x: 8 * x, rec[:6])))
        else: # quad
            rv.append([rec[8]] + list(map(lambda x: 8 * x, rec[:8])))
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

def get_sprite_mergelist(ruleset, typestr):
    "bruteforce a mergelist wrt all mods there"
    ml = []
    for sd in ruleset['extraSprites']:
        if sd['type'].lower() == typestr.lower():
            ml.append(sd)
    ml.sort(key = lambda x: x['_mod_index'])
    return ml
    
_texdump = []
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

def load_geotextures(ruleset, surf_conv, surf_load):
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
    rv = []
    for tbyteseq in tbyteseqs:
        rv.append(surf_conv(tbyteseq, tdat['subX'], tdat['subY'], pal))
    
    for tpatch in ml:
        for tidx, tname in tpatch['files'].items():
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

    
