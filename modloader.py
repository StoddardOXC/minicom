#!/usr/bin/env python3

import math, pprint, sys, os, copy, fnmatch
import yaml

FALLBACK_LANG = 'en-US'

def yamload(path):
    return yaml.load(open(path, "rb"), Loader = yaml.CLoader)

class Finder(object):
    # This deals with paths, directories and their existence only.
    #
    # reimplements stuff from Engine/CrossPlatform.cpp
    # http://openxcom.org/forum/index.php/topic,3617.0.html
    # XDG_ stuff see https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
    # in many cases there are same dirs in both datadirs and homedirs. this creates some confusion.
    #
    # and they might belong to completely different instances of OX/OXE/OXEM.
    # so we only use the first existing dir in the corresponding dirlists.
    #
    def __init__(self, cfgdir=None, userdir = None, datadir = None, force = False):
        # dirs are in order of importance, descending.
        self.datadirs = []
        self.userdirs = []
        self.cfgdirs = []
        if sys.platform.startswith('linux') or sys.plaform == 'freebsd':
            # data dirs
            self.userdirs.append(os.path.join(os.environ["HOME"], ".local/share/openxcom"))
            xdg_datadirs = os.environ.get("XDG_DATA_DIRS", "").split(":")
            for dirpath in xdg_datadirs:
                self.datadirs.append(os.path.join(dirpath, "openxcom"))
            self.datadirs.append("/usr/local/share/openxcom")
            self.datadirs.append("/usr/share/openxcom")
            # user dirs
            self.userdirs.append(os.path.join(os.environ["HOME"], ".local/share/openxcom"))
            if "XDG_USER_DIR" in os.environ:
                self.userdirs.append(os.path.join(os.environ["XDG_USER_DIR"]), 'openxcom')
            # cfg dirs
            if "XDG_CONFIG_HOME" in os.environ:
                self.cfgdirs.append(os.path.join(os.environ["XDG_CONFIG_HOME"], 'openxcom'))
            else:
                self.cfgdirs.append(os.path.join(os.environ["HOME"], '.config/openxcom'))

        elif sys.platform =='darwin':
            homedir = os.environ["HOME"]
            self.datadirs.append(os.path.join(homedir, "Library/Application Support/OpenXcom"))
            self.datadirs.append("/Users/Shared/OpenXcom/")
            self.homedirs.append(os.path.join(homedir, "Library/Application Support/OpenXcom"))

        elif sys.plaform == 'win32':
            """ ctypes:
                    SHGetFolderPathA
                    PathAppendA
                    GetModuleFileNameA
                    GetCurrentDirectoryA
            (maybe not A)
            http://stackoverflow.com/questions/3858851/python-get-windows-special-folders-for-currently-logged-in-user
            """
        elif sys.platform == 'cygwin':
            pass
        else:
            raise Exception("wtf is '" + sys.platform + "' platform?")

        self.datadirs.append(".")
        self.userdirs.append(".")
        self.cfgdirs.append(".")

        # only processing below. no new dirs.
        ## force if forced
        def set_forced(dirlist, dirpath):
            if dirpath is not None:
                if force:
                    dirlist.clear()
                    dirlist[0] = dirpath
                else:
                    dirlist.insert(0, dirpath)

        set_forced(self.cfgdirs, cfgdir)
        set_forced(self.userdirs, userdir)
        set_forced(self.datadirs, datadir)

        ## cull nonexistents
        def check_dirs(dirlist):
            rv = []
            for d in dirlist:
                d = os.path.normpath(d)
                if d in rv:
                    continue
                if os.path.isdir(d):
                    rv.append(d)
            return rv

        self.datadirs = check_dirs(self.datadirs)
        self.userdirs = check_dirs(self.userdirs)
        self.cfgdirs  = check_dirs(self.cfgdirs)

        # Here might be some heuristics about which datadir to use
        # wrt prefix of a cfgdir where a config file actually exists.
        # I hate this.

        if len(self.datadirs) == 0:
            raise FileNotFoundError("No existing datadir found")
        else:
            self.datadir = self.datadirs[0]

        if len(self.userdirs) == 0:
            raise FileNotFoundError("No existing userdir found")
        else:
            self.userdir = self.userdirs[0]

        if len(self.cfgdirs) == 0:
            raise FileNotFoundError("No existing cfgdir found")
        else:
            self.cfgdir = self.cfgdirs[0]

    def __str__(self):
        return "cfg={!r} user={!r} data={!r}".format(self.cfgdir, self.userdir, self.datadir)
        return "cfg={!r} user={!r} data={!r}".format(self.cfgdirs, self.userdirs, self.datadirs)

    """ Use cases:
        - get the config. returns first config found
          across the defined cfgdirs.

        - load mod resources
          - needs mod root
            - for user mods relative to userdirs:
            - for 'standard' mods relative to datadirs/standard

        - load vanilla resources
          - look everywhere in datadirs
          - the 'common' dir - translations, soldiernames, pathfinding..

        - list a directory - for slash-ending lookups or globs
          slash-ending is just a whatever/* case of a glob.

        core data vs user mod data question.
        the former shouldn't touch userdirs at all.

    """

    @property
    def config(self):
        for d in self.cfgdirs:
            # case-insensivitise this?
            cf = os.path.join(d, 'options.cfg')
            if os.path.isfile(cf):
                return cf
        raise FileNotFoundError("options.cfg in {}".format(self.cfgdirs))

    def glob(self, pathglob, roots):
        """ Basic case-insensitive search for paths.
            Returns a list of files found, pathglob possibly being a fnmatch pattern
            - fname: a partial filepath, possibly with fnmatch patterns in it
            - roots: a list of roots, absolute paths, from where to search
        """

        # split the path into uppercase components
        components = []
        remnant = pathglob.upper()
        while remnant != '':
            dirname, basename = os.path.split(remnant)
            if basename == '': # pathglob ends in a slash: list entire dir
                basename = '*'
            components.insert(0, basename)
            remnant = dirname

        # about 5x speedup on xpiratez if we don't call fnmatch when not needed
        if '?' in pathglob or '*' in pathglob or '[' in pathglob:
            def cmp(a, b):
                return fnmatch.fnmatch(a, b)
        else:
            def cmp(a, b):
                return a == b

        # breadth-first search is simpler, but slower if we have
        # all the stuff in the first root, plus a bunch of irrelevant
        # roots after it.
        candiroots = roots
        for pathcomp in components:
            nextroots = []
            for candiroot in candiroots:
                for direntry in os.listdir(candiroot):
                    if cmp(direntry.upper(), pathcomp):
                        nextroots.append(os.path.join(candiroot, direntry))
            candiroots = nextroots

        return nextroots

    def glob_data(self, pathglob):
        """ match explicitly againt datadirs: used for expanding extResDirs' paths """
        return self.glob(pathglob, self.datadirs)

    def erdglob(self, pathglob, extResDirs):
        """ glob for stuff while loading vanilla/extResDir stuff.

            doubt if we should search for UFO data in userdirs.

        """
        return self.glob(pathglob, [os.path.join(self.datadir, erd) for erd in extResDirs + ['common']])

    @property
    def modlist(self):
        def _dirlist(root, dirname):
            for moddir in os.listdir(os.path.join(root, dirname)):
                modpath = os.path.join(root, dirname, moddir)
                if os.path.isdir(modpath):
                    yield modpath
        for modpath in _dirlist(self.datadir, 'standard'):
            yield modpath
        for modpath in _dirlist(self.userdir, 'mods'):
            yield modpath

class ModMeta(object):
    """ mod metadata container plus couple helper functions """
    def __init__(self, path, finder):
        self.root = path
        self.name = os.path.basename(path)
        self.id = self.name
        self.author = "unknown author"
        self.description = "No description"
        self.master = "xcom1"
        self.isMaster = False
        self.loadResources = []
        self.version = "1.0"
        self.mtime = 0
        self.extResDirs = []

        md_path = os.path.join(path, 'metadata.yml')
        try:
            md = yamload(md_path)
            self._bump_mtime(md_path)
            # optional fields
            self.id = md.get("id", self.id)
            self.master = md.get("master", None)
            self.isMaster = md.get("isMaster", False)
            self.extResDirs = md.get("loadResources", [])
            # required fields
            self.author = md["author"]
            self.description = md["description"]
            self.version = md["version"]
            self.name = md["name"]
        except FileNotFoundError:
            print("no metadata for {}".format(path))

        self.finder = finder
        # expand extResDirs if any
        return
        erds = []
        for erd in self.extResDirs:
            for dp in self.finder.glob_data(erd):
                if os.path.isdir(dp):
                    erds.append(dp)
        self.extResDirs = erds

    def _bump_mtime(self, path):
        mt = os.stat(path).st_mtime
        if mt > self.mtime:
            self.mtime = mt

    def __str__(self):
        return "id={} master={} name={} version={} root={} erd={}".format(
            self.id, self.master, self.name, self.version, self.root, self.extResDirs)

    __repr__ = __str__

    def findall(self, pathglob):
        rv = self.finder.erdglob(pathglob, self.extResDirs) if len(self.extResDirs) > 0 else []
        return self.finder.glob(pathglob, [self.root]) + rv

    def findone(self, pathglob):
        try:
            return self.findall(pathglob)[0]
        except IndexError:
            raise FileNotFoundError("finder={} mod_root={} pathglob={}".format(self.finder, self.root, pathglob))



def merge_globe(left, right):
    left.update(right)
    return left
"""
    A map of unique attribute names in mod yaml doc collections
    to the collections' names

    other special cases:
     - delete in soldiers::soldierNames (res ref)
            probably means the name set should be reset.
     - extraStrings
            handled explicitly, since they require second-tier dict merge
     - extraSprites, extraSounds
            modIndex/modOffset shenanigans
"""
PRIMARY_KEYS = {
    'items': 'type',
    'units': 'type',
    'alienDeployments': 'type',
    'missionScripts': 'type',
    'alienMissions': 'type',
    'ufos': 'type',
    'armors': 'type',
    'regions': 'type',
    'facilities': 'type',
    'interfaces': 'type',
    'craftWeapons': 'type',
    'soldiers': 'type',
    'crafts': 'type',
    'mapScripts': 'type',
    'countries': 'type',
    'MCDPatches': 'type',
    'cutscenes': 'type',
    'musics': 'type',
    'itemCategories': 'type',

    'ufopaedia': 'id',
    'invs': 'id',
    'ufoTrajectories': 'id',
    'alienRaces': 'id',

    'research': 'name',
    'manufacture': 'name',
    'terrains': 'name',

# None means no merge; replace entirely
    # 3.2 too? None for now, need investigation
    'extended': None,
    # appeared in 3.2
    'commendations': None,
    # appeared in 3.1
    'converter': None,
    'difficultyCoefficient': None,
    'aimAndArmorMultipliers': None,
    'statGrowthMultipliers': None,
    'turnAIUseGrenade': None,
    'turnAIUseBlaster': None,
    'constants': None,

    # as of 2.9
    'alienItemLevels': None,
    'startingBase': None,
    'startingTime': None,
    'costEngineer': None,
    'costScientist': None,
    'timePersonnel': None,
    'initialFunding': None,
    'turnAIUseGrenade': None,
    'turnAIUseBlaster': None,
    'difficultyCoefficient': None,
    'fontName': None,
    'alienFuel': None,
    'maxLookVariant': None,
    'maxViewDistance': None,
    'chanceToStopRetaliation': None,
    'tooMuchSmokeThreshold': None,
    'oneHandedPenaltyGlobal': None,
    'kneelBonusGlobal': None,
    'monthlyRatings': None,
    'missionRatings': None,
    'globe': merge_globe,
    'startingConditions': None,

# XcomUtil_StatStrings - a problem where mods introduce arbitrary keys.
# how to merge them?
    'statStrings': None,
}

class ConstraintViolation(Exception):
    pass

def list_to_dict(primarykey, a_list):
    rv = {}
    for item in a_list:
        if item[primarykey] in rv:
            raise ConstraintViolation("list_to_dict({}, {}): item[primarykey]={} is in already".format(
                primarykey, a_list, item[primarykey] ))
        rv[item[primarykey]] = item
    return rv

def dict_to_list(pkey_name, a_dict):
    rv = []
    for v in a_dict.values():
        if pkey_name not in v:
            raise Exception("CantConvertDictToListMissingPKey: {} not in {!r}".format(pkey_name, v))
        rv.append(v)
    return rv

# this is not exactly merge, since anything apart from config lang
# and the fallback lang gets skipped. It's midway between just merging all strings
# and dropping lang info from the ruleset, or loading all the translations,
# so that at least untranslated strings can be detected later.
def merge_extrastrings(mod, left, right):
    ldict = list_to_dict('type', left)
    rdict = list_to_dict('type', right)

    def print_count():
        for lang, sss in ldict.items():
            print("left: {}/{}, {}".format(lang, sss['type'], len(sss['strings'])))
        for lang, sss in rdict.items():
            print("right: {}/{}, {}".format(lang, sss['type'], len(sss['strings'])))

    #print_count()

    for lang in rdict.keys():
        if lang in ldict.keys():
            # TODO: detect replacements
            ldict[lang]['strings'].update(rdict[lang]['strings'])
            print("extraStrings: updated", lang)
        elif lang == mod.lang or lang == FALLBACK_LANG:
            ldict[lang] = { 'type': lang, 'strings': rdict[lang]['strings'] }
            print("extraStrings: added", lang)
        else:
            print("extraStrings: skipped", lang)

    #print_count()

    return list(ldict.values())

def merge_extrasprites(mod, left, right):
    """ seems like extrasprites' type is actually a type rather than a key.

        soo, extrasprites is a list of dicts .. no dammit. gotta dig moar into ze code.
        [ {...},
          {'files': {0: 'Resources/UI/invpaste_empty.png'}, 'height': 16, 'singleImage': True, 'type': 'InvPasteEmpty', 'width': 16},
          {'files': {-4: 'Resources/Weapons/Terror.png'}, 'height': 96, 'subX': 32, 'subY': 48, 'type': 'BIGOBS.PCK', 'width': 64},
          {'files': {-5: 'Resources/Weapons/Zombie.png'}, 'height': 48, 'type': 'BIGOBS.PCK', 'width': 32},
          ]
        and how tis used?

        mod.cpp has:
            std::map<std::string, ExtraStrings *> _extraStrings;

            std::map<std::string, Surface*> _surfaces;
            std::map<std::string, SurfaceSet*> _sets;
            std::map<std::string, SoundSet*> _sounds;
            std::map<std::string, Music*> _musics;

        extraSprites yaml parser handler says:
            std::string type = (*i)["type"].as<std::string>();
            std::auto_ptr<ExtraSprites> extraSprites(new ExtraSprites());
            if (type != "TEXTURE.DAT")
                extraSprites->load(*i, _modOffset);
            else
                extraSprites->load(*i, 0);
            _extraSprites.push_back(std::make_pair(type, extraSprites.release()));
            _extraSpritesIndex.push_back(type);

        Mod::loadExtraResources() says:
            if single image:
                if type not in


    """
    for es in right:
        es['_mod_index'] = mod.index
        esfiles = {}
        for idx, path in es['files'].items():
            expath = mod.findone(path)
            #print(mod.root, mod.index, idx, path, expath)
            if expath is None:
                sys.exit(0)
            esfiles[idx] = expath
        es['files'] = esfiles
        left.append(es)
    return left

def merge_extrasounds(mod, left, right):
    print(" merge_extrasounds(): skipping")
    return left

def merge(mod_idx, primarykey, left, right, show_diff_for = []):
    """ drop stuff from left that is marked for deletion in right
        then replace/update the rest according to the primarykey

        return the values() instead of hash. eww.

        also if primarykey is none, just replace.
    """
    if primarykey is None:
        print("      overwrite all")
        if type(right) is dict:
            right['_mod_index'] = mod_idx
        elif type(right) is list:
            for it in right:
                if type(it) is dict:
                    it['_mod_index'] = mod_idx
        return right
    elif callable(primarykey):
        return primarykey(left, right)
    left_dict = list_to_dict(primarykey, left)
    deleted = []
    for item in right:
        if 'delete' in item:
            assert type(item) is dict
            assert len(item) == 1
            try:
                del left_dict[item['delete']]
                print("      del", item['delete'])
            except KeyError:
                print("      del {}: missing".format(item['delete']))
            deleted.append(item['delete'])
        else:
            itype = item[primarykey]
            if itype in left_dict:
                print("      mod", itype)
                if itype in show_diff_for:
                    print("original: {}\n\n".format(pprint.pformat(left_dict[itype])))
                    print("update:   {}\n\n".format(pprint.pformat(item)))
                    left_dict[itype].update(item)
                    print("new:      {}\n\n".format(pprint.pformat(left_dict[itype])))
                else:
                    left_dict[itype].update(item)
            else:
                if itype in deleted:
                    print("      add", itype)
                left_dict[itype] = item
            left_dict[itype]['_mod_index'] = mod_idx
    return dict_to_list(primarykey, left_dict)

def expand_paths(mod, rulename, rule):
    if rulename == 'globe':
        if 'data' in rule:
            rule['data'] = mod.findone(rule['data'])
            return rule
    elif rulename == 'fontName':
        rule = mod.findone(os.path.join('Language',rule)) # dammit, another implicit rule
        return rule
    elif rulename == 'cutscenes':
        for scene in rule:
            if 'videos' in scene:
                vidpaths = []
                for vp in scene['videos']:
                    vidpaths.append(mod.findone(vp))
                    print( vidpaths )
                scene['videos'] = vidpaths
            if 'slideshow' in scene:
                for slide in scene['slideshow']['slides']:
                    slide['imagePath'] = mod.findone(slide['imagePath'])
                    print( slide['imagePath'] )
        return rule
    elif rulename == 'soldiers':
        for soldier in rule:
            snames = []
            for sname in soldier['soldierNames']:
                if sname == 'delete':
                    snames = []
                else:
                    for fname in mod.findall(sname):
                        if fname.lower().endswith('.nam'):
                            snames.append(fname)
            soldier['soldierNames'] = snames
        return rule
    else:
        return rule

def yamdirload_and_merge(mod, ruleset, rul_dir, suffix = '.rul', printdiff = True):
    for d in os.listdir(rul_dir):
        if d.endswith(suffix):
            rulpath = os.path.join(rul_dir, d)
            print("  read ", rulpath)
            rul = yamload(rulpath)
            for k, v in rul.items():
                v = expand_paths(mod, k, v)
                if k in ruleset.keys():
                    print("   *", k)
                else:
                    print("   +", k)
                    if type(v) is dict:
                        ruleset[k] = {}
                    elif type(v) is list:
                        ruleset[k] = []
                    else:
                        ruleset[k] = None
                #if printdiff:
                    #print("{}: merge '{}'".format(rulpath, k))
                if k == 'extraStrings':
                    ruleset[k] = merge_extrastrings(mod, ruleset[k], v)
                elif k == 'extraSprites':
                    ruleset[k] = merge_extrasprites(mod, ruleset[k], v)
                elif k == 'extraSounds':
                    ruleset[k] = merge_extrasounds(mod, ruleset[k], v)
                else:
                    pkey = PRIMARY_KEYS[k]
                    ruleset[k] = merge(mod.index, PRIMARY_KEYS[k], ruleset[k], v)
        elif False:
            print("Ign", os.path.join(path, d))


def load_vanilla(mod):
    # Mod.cpp::loadVanillaResources()
    def fi(pathglob):
        return mod.findone(pathglob)

    SI_TEMPLATE = { "type": None, "width": 320, "height": 200, "singleImage": True, "resType": None, "files": { 0: None }}
    def def_buncha_files(pathglob, _type=None, resType=None, fail=True):
        rv = []
        fpaths = mod.findall(pathglob)
        if fail and len(fpaths) == 0:
            raise FileNotFoundError(pathglob)
        for fpath in fpaths:
            t = copy.deepcopy(SI_TEMPLATE)
            t["type"] = os.path.split(fpath)[1] if _type is None else _type
            t["resType"] = fpath[-3:].upper() if resType is None else resType
            t["files"][0] = fpath
            rv.append(t)
        return rv

    surfaces = [
        { "type":"INTERWIN.DAT", "width": 160, "height": 600, "subX": 160, "resType": "SCR", "files": { 0: fi("GEODATA/INTERWIN.DAT") }},
    ]

    surfaces += def_buncha_files("GEOGRAPH/*.SCR", fail = False)
    surfaces += def_buncha_files("GEOGRAPH/*.BDY", fail = False)
    surfaces += def_buncha_files("GEOGRAPH/*.SPK", fail = False)

    surfaces += [
        { "type": "TEXTURE.DAT",    "subX": 32, "subY": 32, "files": { 0: fi("GEOGRAPH/TEXTURE.DAT") }},
        { "type": "BASEBITS.PCK",   "subX": 32, "subY": 40, "files": { 0: fi("GEOGRAPH/BASEBITS.PCK") }},
        { "type": "INTICON.PCK",    "subX": 32, "subY": 40, "files": { 0: fi("GEOGRAPH/INTICON.PCK") }},
        { "type": "SCANG.DAT",      "subX":  4, "subY":  4, "files": { 0: fi("GEODATA/SCANG.DAT") }},
    # sounds: GEO.CAT: SOUND2_CAT | SAMPLE.CAT; BATTLE.CAT: SOUND1.CAT | SAMPLE2.CAT; dir: SOUND/
    # + intro.cat, sample3.cat

    #
    # Mod.cpp::loadBattlescapeResources()
        { "type": "SPICONS.DAT",    "subX": 32,  "subY": 24, "files": { 0: fi("UFOGRAPH/SPICONS.DAT") }},
        { "type": "CURSOR.PCK",     "subX": 32,  "subY": 40, "files": { 0: fi("UFOGRAPH/CURSOR.PCK") }},
        { "type": "SMOKE.PCK",      "subX": 32,  "subY": 40, "files": { 0: fi("UFOGRAPH/SMOKE.PCK") }},
        { "type": "HIT.PCK",        "subX": 32,  "subY": 40, "files": { 0: fi("UFOGRAPH/HIT.PCK") }},
        { "type": "X1.PCK",         "subX": 128, "subY": 64, "files": { 0: fi("UFOGRAPH/X1.PCK") }},
        { "type": "MEDIBITS.DAT",   "subX": 52,  "subY": 58, "files": { 0: fi("UFOGRAPH/MEDIBITS.DAT") }},
        { "type": "DETBLOB.DAT",    "subX": 16,  "subY": 16, "files": { 0: fi("UFOGRAPH/DETBLOB.DAT") }},
    ]

    # load all of the terrain. we're bankin! (maybe later)
    "TERRAIN/*.PCK" # 32x40

    "UNITS/*.PCK" # 32x40 except BIGOBS.PCK which is 32x48

    #if os.flen(chrys.tab) < 225*2:
    #    raise Exception("Invalid CHRYS.PCK, please patch your X-COM data to the latest version")

    try:
        loftemps = fi("TERRAIN/LOFTEMPS.DAT") # tftd
    except FileNotFoundError:
        loftemps = fi("GEODATA/LOFTEMPS.DAT") # ufo

    surfaces += [
        { "type": "LOFTEMPS.DAT", "resType": "loftemps", "subX": 16, "subY": 16, "files": { 0: loftemps }},
        { "type": "TAC00.SCR", "width": 320, "height": 200, "singleImage": True, "files": { 0: fi("UFOGRAPH/TAC00.SCR")}},
    ]

    # mildly annoying lbm stuff skipped.

    palettes = { }
    offs = 0
    offstep = 768+6
    pfile = fi("GEODATA/PALETTES.DAT")
    for p in  ( "PAL_GEOSCAPE", "PAL_BASESCAPE", "PAL_GRAPHS", "PAL_UFOPAEDIA", "PAL_BATTLEPEDIA"):
        palettes[p] = { "file": pfile, "offs": offs, "size": 256*3 }
        offs += offstep
    palettes["BACKPALS.DAT"] = { "file": fi("GEODATA/BACKPALS.DAT"), "offs": 0, "size": 128*3 }

    palettes["PAL_BATTLESCAPE"] = { "file": fi("GEODATA/PALETTES.DAT"), "offs": 4*offstep, "size": 256*3 }
    # last 16 greyscale and fixup not implemented yet.

    # optional stuff, means, skip if not found (think that has to do with tftd)

    for fpath in """UFOGRAPH/TAC01.SCR
                    UFOGRAPH/DETBORD.PCK
                    UFOGRAPH/DETBORD2.PCK
                    UFOGRAPH/ICONS.PCK
                    UFOGRAPH/MEDIBORD.PCK
                    UFOGRAPH/SCANBORD.PCK
                    UFOGRAPH/UNIBORD.PCK""".split():
        surfaces += def_buncha_files(fpath, None, "SPK", fail = False)

    for tftd_surf in def_buncha_files("UFOGRAPH/*.BDY", fail = False):
        print(tftd_surf)
        fn = os.path.split(tftd_surf["files"][0]).upper()
        _type = fn[:-3]
        if fn.startswith('MAN'):
            _type += 'SPK'
        elif _type == 'TAC01.':
            _type = 'TAC01.SCR'
        else:
            _type += 'PCK'
        tftd_surf["type"] = _type
        surfaces.append(tftd_surf)

    # // Load Battlescape inventory: UFOGRAPH/*.SPK
    surfaces += def_buncha_files("UFOGRAPH/*.SPK")

    # crazy stuff about Options::battleHairBleach


    # Applies necessary modifications to vanilla resources.
    # Mod::modResources()

    # bigger geoscape background - tiles GEOBORD.SCR x3 in w and h
    # saves as ALTGEOBORD.SCR

    # some stuff with ALTBACK07.SCR being made from GEOGRAPH/BACK07.SCR
    #

    # soldier stat screens:
    # shenanigans with BACK06.SCR  - base info screen
    # same thing with UNIBORD.PCK - battlescape info screen?

    # duplicate the HANDOB.PCK into HANDOB2.PCK:
    # // handob2 is used for all the left handed sprites.
    surfaces += [
        { "type": "HANDOB02.PCK", "subX": 32, "subY": 40, "files": { 0: fi("UNITS/HANDOB.PCK") }},
    ]

    for surf in surfaces:
        surf["_mod_index"] = mod.index

    # load std trans as extraStrings so that there are no extra entity types to merge
    try:
        lang = mod.lang
        trans = yamload(fi(os.path.join('Language', lang + '.yml')))
    except FileNotFoundError:
        lang = FALLBACK_LANG
        trans = yamload(fi(os.path.join('Language', lang + '.yml')))

    return { 'extraSprites': surfaces, 'extraStrings': [{ 'type': lang, 'strings': trans[lang] }], '_palettes': palettes }

def load(finder):
    config = yamload(finder.config)
    lang = config['options'].get('language', FALLBACK_LANG)

    present_mods = dict((mod.id, mod) for mod in [ ModMeta(p, finder) for p in finder.modlist ])

    # gather all active mods into a set
    active_mods = set()
    for mod in config['mods']:
        if mod['active']:
            modinfo = present_mods[mod['id']]
            active_mods.add(modinfo)
            if modinfo.master not in (None, '*'):
                master_mod = present_mods[modinfo.master]
                if not master_mod.isMaster:
                    raise Exception("MasterModIsNotAMasterError: {} is not a master as {} expects".format(
                                        master_mod.id, modinfo.id))
                active_mods.add(master_mod)

    # resolve dependencies into a load order
    def find_least_dependent(modset, masters):
        for mod in modset:
            if mod.master is None and mod.isMaster:
                return mod
            elif mod.master == '*':
                if len(masters) > 0:
                    return mod
            elif mod.master in map(lambda x: x.id, masters):
                return mod

        raise Exception("RequiredMasterMissing: mod.master={} load_order=[{}]".format(
                            mod.master, ','.join(map(lambda x: x.id, masters))))
    load_order = []
    mod_index = 0
    while len(active_mods) > 0:
        mod = find_least_dependent(active_mods, load_order)
        load_order.append(mod)
        mod.index = mod_index
        mod_index += 1
        mod.lang = lang # set preferred lang. fallback is 'en-US' (FALLBACK_LANG).
        active_mods.remove(mod)

    ruleset = {}
    for mod in load_order:
        print("\nLoading {}, extResDirs={}".format(mod.root, mod.extResDirs))
        if len(mod.extResDirs) > 0:
            if len(ruleset) > 0:
                raise WTF
            ruleset = load_vanilla(mod)
        yamdirload_and_merge(mod, ruleset, mod.root)
        rul_dir = os.path.join(mod.root, 'Ruleset')
        if os.path.isdir(rul_dir):
            yamdirload_and_merge(mod, ruleset, rul_dir)

    #ruleset['extraStrings'] = [] # skip for now to ease the load on the editor
    ruleset['_mod_meta'] = []
    for mod in load_order:
        ruleset['_mod_meta'].append({
            'root': mod.root,
            'extResDirs': mod.extResDirs,
            'id': mod.id,
            'index': mod.index,
            'name' : mod.name,
            })

    return ruleset

def main():
    userdir = os.path.join(sys.argv[1], 'user')
    datadir = sys.argv[1]
    cfgdir  = userdir
    ofname = 'ruleset.py' if len(sys.argv) < 3 else sys.argv[2]

    finder = Finder(cfgdir, userdir, datadir)
    print(finder)
    print(finder.config)
    ruleset = load(finder)

    with open(ofname, "w") as f:
        f.write("ruleset = {\n ")
        f.write(pprint.pformat(ruleset, width=320)[1:])

if __name__ == '__main__':
    main()
