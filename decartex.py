#!/usr/bin/env python3


import math, pickle, pprint, sys, os, collections
import render2d
from render2d import bufpal2surface, file2surface
import fileformats

from ruleset import ruleset

DEG2RAD_MTP = math.pi / 180.0

SphCoord2 = collections.namedtuple('SphCoord2', 'lon lat')
Coord2 = collections.namedtuple('Coord2', 'x y')
Coord3 = collections.namedtuple('Coord3', 'x y z')

def rotfoo(lon, lat, lonzero, latzero):
    """ http://stackoverflow.com/questions/5278417/rotating-body-from-spherical-coordinates
    The equations for (x,y,z) (spherical-to-cartesian) are
    
    x = r sin θ cos φ
    y = r sin θ sin φ
    z = r cos θ
    
    The equations for rotating (x,y,z) to new points (x', y', z') around the x-axis by an angle α are
    
    x' = x
       = r sin θ cos φ
    y' = y cos α - z sin α
       = (r sin θ sin φ) cos α - (r cos θ) sin α
    z' = y sin α + z cos α
       = (r sin θ sin φ) sin α + (r cos θ) cos α

    The equations for (r, θ, φ) (cartesian-to-spherical) are

    r' = sqrt(x'2 + y'2 + z'2)
       = r
    θ' = cos-1(z'/r')
       = cos-1(sin θ sin φ sin α + cos θ cos α)
    φ' = tan-1(y'/x')
       = tan-1(tan φ cos α - cotan θ sin α sec φ)
       = atan2( sin θ sin φ cos α - cos θ sin α, sin θ cos φ)

    here we first shift longtiude
    then rotate about x by lonshift which is to be in [-90, 90].

    note that the above is physics convention: lon in phi, lat is theta.
    """
    
    theta = lat * math.pi / 180
    phi = math.fmod(lon + lonshift, 360) * math.pi / 180
    alpha = latzero * math.pi / 180
    
    theta1 = math.acos(math.sin(theta)*math.sin(phi)*math.sin(alpha) + math.cos(theta)*math.cos(alpha))
    phi1 = math.atan2(math.sin(theta)*math.sin(phi)*math.cos(alpha) - math.cos(theta)*math.sin(alpha), 
                            math.sin(theta)*math.cos(phi))
    nlon = 180 * phi1/math.pi
    nlat = 180 * theta1/math.pi
    
    return nlon, nlat
    

# degs_below_horizon : brightness_factor_wrt_noon
TWIMAP = [
    (0, 0.75 ),
    (6.0, 0.5 ),
    (12.0, 0.25 ),
    (18.0, 0.0 ),
]

# hmm hmm
# standard/xcom1/globe.rul sez GEODATA/WORLD.DAT
# so that's relative to 
#
# user/mods/Piratez/Ruleset/Piratez_Planet.rul sez Resources/Globe/IMPROVEDGLOBE.DAT f/ex
# so that's relative to the mod root.
#


# convert lon+lat in degrees
# to cartesian coordinates on a unit sphere.
# (x axis at lon=0, xy both at equator, z points north)
# return bytes of single-precision float triplet (x,y,z)
def geo2carte(coord):
    theta = coord.lon * DEG2RAD_MTP
    phi   = coord.lat * DEG2RAD_MTP
    return Coord3(math.sin(theta) * math.cos(phi),
                  math.sin(theta) * math.sin(phi),
                  math.cos(theta))

class SomeStat(object):
    def __init__(self, name):
        self.name = name
        self.vmax = -1e17
        self.vmin = 1e17
    def update(self, value):
        if self.vmax < value:
            self.vmax = value
        if self.vmin > value:
            self.vmin = value
    def __str__(self):
        return "{} in [{:0.2f} {:0.2f}]".format(self.name, self.vmin, self.vmax)

stat_x = SomeStat("x")
stat_y = SomeStat("y")
stat_lon = SomeStat("lon")
stat_lat = SomeStat("lat")

class VertexList(object):
    def __init__(self):
        self._list = []

    def add(self, vtx):
        self._list.append(vtx)
        return len(self._list) - 1
        

# duh. should map spherical coordinates to x,y e (-1, 1)
# kinda like NDC coords.
# convert lon+lat to EPSG:54003 — World Miller Cylindrical
# cartographic projection
# return bytes of single-precision float pair (x,y)
def sph2wmc(coord):
    HC = 2.303413 # max(abs(y)) in WMC
    global stat_x, stat_y, stat_lon, stat_lat
    
    lam = math.pi * coord.lon / 180.0
    phi = math.pi * coord.lat / 180.0

    y = 5.0 * math.log(math.tan(math.pi/4.0 + 2.0*phi/5.0)) / 4.0    
    x = (coord.lon - 180) / 180.0
    y = y / HC

    stat_x.update(x)
    stat_y.update(y)
    stat_lon.update(coord.lon)
    stat_lat.update(coord.lat)

    return Coord2(x, y)

def sph2equirect(coord, coord0):
    global stat_x, stat_y, stat_lon, stat_lat
    coord = SphCoord2((coord.lon - coord0.lon) % 360, coord.lat)#(coord.lat - coord0.lat) % 90)
    lam = math.pi * coord.lon / 180.0
    phi = math.pi * coord.lat / 180.0
    
    # equirect proj
    phi_1 = math.pi/4 # +/- 45 deg lat
    x = coord.lon * math.pi * math.cos(phi_1) / 180.0
    y = phi

    stat_x.update(x)
    stat_y.update(y)
    stat_lon.update(coord.lon)
    stat_lat.update(coord.lat)

    return Coord2(x, y)
    

def polycount(polygons):
    ptex = {}
    pcnt = {}
    for poly in polygons:
        ptex[poly[0]] = ptex.get(poly[0], 0) + 1
        vcount = (len(poly) - 1)/2
        pcnt[vcount] = pcnt.get(vcount, 0) + 1

    pprint.pprint(ptex)
    pprint.pprint(pcnt)

# http://stackoverflow.com/questions/4870393/rotating-coordinate-system-via-a-quaternion

# split quads into tris
# hmm. how does texturing go? is it ndc-fixed? yep, it is. so just split and convert into 
# indexed arrays of vertices and triangles. no texcoords whatsoever.
# ds_threshold is parts of degree to merge vertices. None is exact equality. 
# Use 9 since ruls doesnt' seem to have more than 1/8ths degree precision
def vertex_merge(polygons, polylines, ds_threshold = None):
    def delta_sigma(v0, v1):
        # great circle arc angle via haversine formula (radians)
        # sensitive to antipodal points, irrelevant here.
        # https://en.wikipedia.org/wiki/Great-circle_distance#Computational_formulas
        lambda0 = v0.lon * math.pi / 180.0
        phi0 = v0.lat * math.pi / 180.0
        lambda1 = v1.lon * math.pi / 180.0
        phi1 = v1.lat * math.pi / 180.0
        havdphi = math.sin((phi1 - phi0) / 2.0)
        havdlam = math.sin((lambda1 - lambda0) / 2.0)
        return 2.0 * math.asin(math.sqrt( 
              havdphi * havdphi + math.cos(phi0) * math.cos(phi1) * havdlam * havdlam))
    
    vertices = []
    pgone_cvt = []
    pline_cvt = []
    
    ivtx = 0
    # index all vertices
    # polygons
    for poly in polygons:
        texid = poly[0]
        vertices.append(SphCoord2(poly[1], poly[2]))
        vertices.append(SphCoord2(poly[3], poly[4]))
        vertices.append(SphCoord2(poly[5], poly[6]))
        pgone_cvt.append((texid, ivtx, ivtx + 1, ivtx + 2))
        if len(poly) == 7: # a tri
            ivtx += 3
        elif len(poly) == 9: # a quad
            vertices.append(SphCoord2(poly[7], poly[8]))
            pgone_cvt.append((texid, ivtx + 2, ivtx + 3, ivtx))
            ivtx += 4
        else:
            raise Exception("polygon not quad or tri")

    # polylines
    for pline in polylines:
        if len(pline) < 4 or len(pline) % 2 != 0:
            raise Exception("pline len {}".format(len(pline)))
        pl_cvt = []
        for lon, lat in zip(pline[::2], pline[1::2]):
            vertices.append(SphCoord2(lon, lat))
            pl_cvt.append(ivtx)
            ivtx += 1
        pline_cvt.append(tuple(pl_cvt))
    
    #return vertices, pgone_cvt, []
    
    # todo: merge regions', countries' and missionzones' vertices here too.
    # also detect somehow cities: i think texture -1 is it, rest negative texids
    # are hidden pois. (alien bases positions hardcoded? really?)
    # missionZone def: lonMin, lonMax, latMin, latMax [, texId [, name]]

    if ds_threshold is not None:
        def eq_test(v0, v1):
            DELTA_SIGMA_THRESHOLD = (1.0/ds_threshold) * math.pi / 180.0
            return delta_sigma(v0, v1) < DELTA_SIGMA_THRESHOLD
    else:
        def eq_test(v0, v1, thresh=0.0001):
            return abs(v0.lon-v1.lon) < thresh and abs(v0.lat-v1.lat) < thresh

    # merge adjacent enough vertices, 
    # O(n^2), but whatever, that's preprocessing.
    # for each vertex look what vertices can be mapped to it
    # (which vertices can be replaced by this vertex)
    vidx_merge_map = {} # key: index of the vertex that was merged away.
                        # value: index of the vertex it was mapped to (or key if wasn't mapped).

    idxset = set(range(len(vertices)))
    vidx_merge_map = {}
    for vidx in range(len(vertices)):
        if vidx in vidx_merge_map:  # has already been merged, skip.
            continue
        merged = set()
        for candidate in idxset:
            if eq_test(vertices[vidx], vertices[candidate]):
                vidx_merge_map[candidate] = vidx
                merged.add(candidate)

        idxset.difference_update(merged) # remove merged ones from further consideration.
    
    unique_vertex_indices = set(vidx_merge_map.values())
    
    print("v_len={} mm_len = {}, uniq_len = {}".format(len(vertices), 
                        len(vidx_merge_map), len(unique_vertex_indices)))
    #open('vertices.py', 'w').write(pprint.pformat(vertices))
    #open('vertices-merge.py', 'w').write(pprint.pformat(vidx_merge_map))
    #open('vertices-uniq.py', 'w').write(pprint.pformat(unique_vertex_indices))

    short_vidx_map = {} # key: original vertex index, value: vertex index in the short_vertex_list
    short_vertex_list = []
    idx = 0
    for oidx in vidx_merge_map.values():
        short_vertex_list.append(vertices[oidx])
        short_vidx_map[oidx] = idx
        idx += 1

    tri_list = [] 
    for tex, a, b, c in pgone_cvt:
        tri_list.append((tex, 
            short_vidx_map[vidx_merge_map[a]],
            short_vidx_map[vidx_merge_map[b]],
            short_vidx_map[vidx_merge_map[c]]))

    lin_list = []
    for pline in pline_cvt:
        lin_list.append(list(map(lambda idx: short_vidx_map[vidx_merge_map[idx]], pline)))

    return short_vertex_list, tri_list, lin_list


# projects primitives, fixes up polar areas, splits
# vertical border spanning primitives.
def wmc_project(vertices, tris, plines, lonshift = 0):
    vtxlist = []
    # first pass:
    # do the projection
    # split triangles that has pole as one of the vertices
    def add_vertex(c):
        vtxlist.append(c)
        return len(vtxlist) - 1 

    def is_pole(v):
        return abs(abs(v.lat) - 90) < 0.0001

    # do plines:
    plines_p = []
    for pl in plines:
        pl_p = []
        for vtxi in pl:
            vtx = SphCoord2(math.fmod(vertices[vtxi].lon + lonshift, 360), vertices[vtxi].lat)
            vtxp = sph2wmc(vtx)
            pl_p.append(add_vertex(vtxp))
        # now split around vborders
        plines_p.append(pl_p)

    def project_and_pole_split(tri):
        tex, ai, bi, ci = tri

        def pole_y(v):
            return 1 if v.lat > 0 else -1

        a = SphCoord2(math.fmod(vertices[ai].lon + lonshift, 360), vertices[ai].lat)
        b = SphCoord2(math.fmod(vertices[bi].lon + lonshift, 360), vertices[bi].lat)
        c = SphCoord2(math.fmod(vertices[ci].lon + lonshift, 360), vertices[ci].lat)

        c0 = sph2wmc(a)
        c1 = sph2wmc(b)
        c2 = sph2wmc(c)
        c3 = None
        c4 = None

        if is_pole(a):
            # split c0 into c3, c4; 
            # resulting tris would be c3 c1 c2; c4 c3 c2.
            c1i = add_vertex(c1)
            c2i = add_vertex(c2)
            c3i = add_vertex(Coord2(c1.x, pole_y(a)))
            c4i = add_vertex(Coord2(c2.x, pole_y(a)))
            return [(tex, c3i, c1i, c2i), (tex, c4i, c3i, c2i)]
        elif is_pole(b):
            # split c1 into c3, c4; 
            # resulting tris would be c0 c3 c2; c2 c3 c4.
            c0i = add_vertex(c0)
            c2i = add_vertex(c2)
            c3i = add_vertex(Coord2(c0.x, pole_y(b)))
            c4i = add_vertex(Coord2(c2.x, pole_y(b)))
            return [(tex, c0i, c3i, c2i), (tex, c2i, c3i, c4i)]
        elif is_pole(c):
            # split c2 into c3, c4; 
            # resulting tris would be c0 c1 c3; c1 c3 c4.
            c0i = add_vertex(c0)
            c1i = add_vertex(c1)
            c3i = add_vertex(Coord2(c0.x, pole_y(c)))
            c4i = add_vertex(Coord2(c1.x, pole_y(c)))
            return [ (tex, c0i, c1i, c3i), (tex, c1i, c3i, c4i) ]
        else: # no split
            c0i = add_vertex(c0)
            c1i = add_vertex(c1)
            c2i = add_vertex(c2)
            return [(tex, c0i, c1i, c2i)]
    
    # second pass
    # split triangles that span vertical borders
    # of the projection
    def vertisplit(tri):
        # how do we detect them?
        # well, we just split any triangle across 
        # its longest side vertically and keep the split
        # if the sum of the perimeters of the resulting ones
        # is less than the perimeter of the original.
        #
        # split is the wrong word here. It's not split,
        # it's create two triangles pretending there are no borders
        # so that one of them has one out-of-borders vertex and the
        # other has two.
        #
        # then compare perimeters of the original and one of the new
        # (the new ones are identical)
        #
        # dumbest brute-force approach follows (uses squared perimeters
        # since the condition should hold:
        #
        def l_square(ai, bi):
            dx = vtxlist[ai].x - vtxlist[bi].x
            dy = vtxlist[ai].y - vtxlist[bi].y
            return  dx * dx + dy * dy
            
        def p_square(tri):
            tex, ai, bi, ci = tri
            return l_square(ai, bi) + l_square(bi, ci) + l_square(ci, ai)
        
        tex, ai, bi, ci = tri
        a = vtxlist[ai]
        b = vtxlist[bi]
        c = vtxlist[ci]
        l2_ab = l_square(ai, bi)
        l2_bc = l_square(bi, ci)
        l2_ca = l_square(ci, ai)
        
        if max(l2_ab, l2_bc, l2_ca) < 2:
            # skip obviously non-spanning tris.
            return [ tri ]
        
        if l2_ab < min(l2_bc, l2_ca):
            # ab is the shortest. -> split the other two -> 'cut off' vertex C.
            cutoff = c
            cutoff_i = ci
            rest = (a, b)
            resti = (ai, bi)
        elif l2_bc < l2_ca:
            # bc is the shortest -> 'cut off' A
            cutoff = a
            cutoff_i = ai
            rest = (b, c)
            resti = (bi, ci)
        else:
            # ca is the shortest -> 'cut off' B
            cutoff = b
            cutoff_i = bi
            rest = (c, a)
            resti = (ci, ai)
        
        if cutoff.x > 0:
            tri0_cut = add_vertex(Coord2(cutoff.x - 2, cutoff.y))
            tri1_r0  = add_vertex(Coord2(rest[0].x + 2, rest[0].y))
            tri1_r1  = add_vertex(Coord2(rest[1].x + 2, rest[1].y))
        else:
            tri0_cut = add_vertex(Coord2(cutoff.x + 2, cutoff.y))
            tri1_r0  = add_vertex(Coord2(rest[0].x - 2, rest[0].y))
            tri1_r1  = add_vertex(Coord2(rest[1].x - 2, rest[1].y))

        tri0 = (tex, tri0_cut, resti[0], resti[1])
        tri1 = (tex, cutoff_i, tri1_r0, tri1_r1)
        
        if p_square(tri) > p_square(tri0):
            # TODO: clip the new triangles by the vertical borders.
            # this will result in 3 triangles and 4 new vertices.
            
            return [tri0, tri1]
        return [ tri ]

    poleextended_tris = []
    for tri in tris:
        poleextended_tris.extend(project_and_pole_split(tri))

    vertisplit_tris = []
    for tri in poleextended_tris:
        vertisplit_tris.extend(vertisplit(tri))

    # last pass: remove unused vertices
    # maybe merge adjacent ones
    # TODO.
    if 0:
        ni = 0
        smap = {}
        slist_tris = []
        for tri in vertisplit_tris:
            tex, ai, bi, ci = tri
            smap[ni + 0] = ai
            smap[ni + 1] = bi
            smap[ni + 2] = ci
            slist_tris.append(tex, ni, ni + 1, ni + 2)
            ni += 3
        vtx_shortlist = []
        for i in range(ni + 1):
            vtx_shortlist.append(vtxlist[smap[i]])

    return vtxlist, vertisplit_tris, plines_p

def wmc_project_ll(lon, lat, lonshift):
    return sph2wmc(SphCoord2(math.fmod(lon + lonshift, 360), lat))


def extract_poi(pd, vtxlist, lonshift, trans):
    rv = []
    def is_point_zone(mzone):
        return mzone[0] == mzone[1] and mzone[2] == mzone[3]
    mzquads = []
    for reg in pd['regions']:
        if 'missionZones' not in reg:
            continue
        mztype = reg['type']
        #print(mztype)
        for mzlist in reg['missionZones']:
            for mzone in mzlist:
                if len(mzone) == 4:
                    # todo: merge into wmc_project() to handle vertisplit
                    lon0, lon1, lat0, lat1 = mzone
                    # this results in rects anyway because projection is cylindrical
                    
                    mzquads.append((wmc_project_ll(lon0, lat0, lonshift),
                                    wmc_project_ll(lon1, lat0, lonshift),
                                    wmc_project_ll(lon1, lat1, lonshift),
                                    wmc_project_ll(lon0, lat1, lonshift)))
                    continue
                if len(mzone) == 5:
                    if is_point_zone(mzone):
                        vtxi = len(vtxlist)
                        vtxlist.append(wmc_project_ll(mzone[0], mzone[2], lonshift))
                        rv.append((vtxi, mzone[4]))
                elif len(mzone) == 6: # city?
                    if is_point_zone(mzone) and mzone[4] == -1:
                        # yep, a city
                        vtxi = len(vtxlist)
                        vtxlist.append(wmc_project_ll(mzone[0], mzone[2], lonshift))
                        rv.append((vtxi, trans.get(mzone[5], mzone[5])))
                    else:
                        print(mzone)
                else:
                    print(mzone)
    return rv, mzquads

def extract_clabels(pd, vtxlist, lonshift, trans):
    rv = []
    for country in pd['countries']:
        vtxi = len(vtxlist)
        vtxlist.append(wmc_project_ll(country['labelLon'], country['labelLat'], lonshift))
        rv.append((vtxi, trans.get(country['type'], country['type'])))
    return rv

"""    
    range = range_nmi * (1 / 60.0) * (M_PI / 180);
    
    void Globe::drawGlobeCircle(double lat, double lon, double radius, int segments)
{
	double x, y, x2 = 0, y2 = 0;
	double lat1, lon1;
	double seg = M_PI / (static_cast<double>(segments) / 2);
	for (double az = 0; az <= M_PI*2+0.01; az+=seg) //48 circle segments
	{
		//calculating sphere-projected circle
		lat1 = asin(sin(lat) * cos(radius) + cos(lat) * sin(radius) * cos(az));
		lon1 = lon + atan2(sin(az) * sin(radius) * cos(lat), cos(radius) - sin(lat) * sin(lat1));
		polarToCart(lon1, lat1, &x, &y);
		if ( AreSame(az, 0.0) ) //first vertex is for initialization only
		{
			x2=x;
			y2=y;
			continue;
		}
		if (!pointBack(lon1,lat1))
			XuLine(_radars, this, x, y, x2, y2, 4);
		x2=x; y2=y;
	}
}
"""
# radius r is in degrees of arc. must be < 180?
def a_circle(clon, clat, r_nmi, nseg  = 96):
    radius = r_nmi * math.pi / (60*180)
    rad_deg = math.pi / 180
    crlon = clon * rad_deg
    crlat = clat * rad_deg
    pline = []
    for si in range(nseg + 2):
        az = (2 * math.pi / nseg ) *  si
        lat = math.asin(math.sin(crlat) * math.cos(radius) + math.cos(crlat) * math.sin(radius) * math.cos(az))
        lon = crlon + math.atan2(math.sin(az) * math.sin(radius) * math.cos(crlat), 
                            math.cos(radius) - math.sin(crlat) * math.sin(lat))
        
        if si == 0:
            continue # why?

        pline.append(SphCoord2(lon / rad_deg, lat / rad_deg))

    return pline

def get_trans(rset, lang):
    for tr in ruleset['extraStrings']:
        if tr['type'] == lang:
            return tr['strings']
    return {}

def main():
    lonshift = float(sys.argv[1])
    latshift = float(sys.argv[2])

    w = 320
    h = 200
    w = 1280
    h = 768
    h = int(0.733 * w)

    trans = get_trans(ruleset, 'en-US')
    textures = fileformats.load_geotextures(ruleset, bufpal2surface, file2surface)
    
    orig_polygons = ruleset['globe'].get('polygons', fileformats.load_world_dat(ruleset['globe']['data']))
    orig_plines   = ruleset['globe']['polylines']
    
    #polycount(pd['globe']['polygons'])

    vertices, triangles, plines = vertex_merge(orig_polygons, orig_plines)
    #np_vertex_convert(vertices)
    def append_circle(lon, lat, rad):
        cpl = a_circle(lon, -lat, rad)
        ppl = []
        for sv in cpl:
            i = len(vertices)
            ppl.append(i)
            vertices.append(sv)
        plines.append(ppl)
    append_circle(55,70,800)
    append_circle(-90,0,800)
    append_circle(-20,30,800)
    append_circle(-60,50,800)
    append_circle(90,0, 800)
    append_circle(135, -40, 800)
    #append_circle(180, 80, 1800)
    
    vtxlist, trilist, plist = wmc_project(vertices, triangles, plines, lonshift)
    poilist, mzquads = extract_poi(ruleset, vtxlist, lonshift, trans)
    countrylabels = extract_clabels(ruleset, vtxlist, lonshift, trans)
    
    print(stat_x, stat_y, stat_lon, stat_lat)

    render2d.init()
    win, ren = render2d.openwindow((w, h))

    poilist = filter(lambda poi: type(poi[1]) is str, poilist) # filter out enemy bases and stuff
    mzquads = [] # don't render mission zones

    render2d.draw_textris(win, ren, vtxlist, trilist, textures, plist, poilist, countrylabels, mzquads)
    
    render2d.loop(win, ren)
    render2d.fini()

if __name__ == '__main__':
    main()