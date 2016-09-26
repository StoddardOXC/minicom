#!/usr/bin/env python3

import math, pprint, sys, os, copy, fnmatch, textwrap
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

        self.cfgfile = None
        for d in self.cfgdirs:
            # case-insensivitise this?
            cf = os.path.join(d, 'options.cfg')
            if os.path.isfile(cf):
                self.cfgfile = cf
                break

        if self.cfgfile is None:
            raise FileNotFoundError("options.cfg in {}".format(self.cfgdirs))

        self.config = yamload(self.cfgfile)

        self.dircache = {}

    def __str__(self):
        return "cfg={!r} user={!r} data={!r} cfgfile={}".format(self.cfgdir, self.userdir, self.datadir, self.cfgfile)

    def listdir(self, path):
        """ cache os.listdir() and str.upper() calls"""
        try:
            return self.dircache[path]
        except:
            dl = [(de, de.upper()) for de in os.listdir(path)]
            self.dircache[path] = dl
            return dl


    """ Use cases:

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
        if '?' in pathglob or '*' in pathglob or '[' in pathglob or pathglob.endswith('/'):
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
                for direntry, DIRENTRY in self.listdir(candiroot):
                    if cmp(DIRENTRY, pathcomp):
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
    """ mod metadata container plus a couple helper functions """
    def __init__(self, path, finder):
        self.root = path
        self.name = os.path.basename(path)
        self.id = self.name
        self.author = "unknown author"
        self.description = "No description"
        self.masterID = "xcom1"
        self.master = None
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
            self.masterID = md.get("master", None)
            if self.masterID == '*':
                self.masterID = None
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
        return "id='{}' master='{}' name='{}' version='{}' root='{}' erd={}".format(
            self.id, self.masterID, self.name, self.version, self.root, self.extResDirs)

    __repr__ = __str__

    def findall(self, pathglob):
        self_list = self.finder.glob(pathglob, [self.root])
        if len(self_list) > 0:
            return self_list
        erd_list = self.finder.erdglob(pathglob, self.extResDirs) if len(self.extResDirs) > 0 else []
        if len(erd_list) > 0:
            return erd_list
        return self.master.findall(pathglob) if self.master is not None else []

        rv = self_list + erd_list + master_list
        if pathglob.endswith('/'):
            print(self.id, pathglob, self.root, erd_list, master_list, self_list, rv)
        return rv

    def findone(self, pathglob):
        try:
            return self.findall(pathglob)[0]
        except IndexError:
            raise FileNotFoundError("finder=({}) mod_root={} pathglob={}".format(self.finder, self.root, pathglob))

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

def merge_extrastrings(mod_idx, left, right):
    ldict = list_to_dict('type', left)
    rdict = list_to_dict('type', right)

    for lang in rdict.keys():
        if lang in ldict.keys():
            ldict[lang]['strings'].update(rdict[lang]['strings'])
            print("extraStrings: updated", lang)
        else:
            ldict[lang] = { 'type': lang, 'strings': rdict[lang]['strings'] }
            print("extraStrings: added", lang)

    return list(ldict.values())

def merge_extrasprites(mod_idx, left, right):
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
        es['_mod_index'] = mod_idx
        left.append(es)
    return left

def merge_extrasounds(mod_idx, left, right):
    print(" merge_extrasounds(): skipping")
    return left

def merge_globe(mod_idx, left, right):
    left.update(right)
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
        return primarykey(mod_idx, left, right)
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
            try:
                itype = item[primarykey]
            except KeyError:
                print("item '{}' missing primarykey of '{}".format(item, primarykey))
                raise
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
    elif rulename == 'fontName':
        rule = mod.findone(os.path.join('Language',rule)) # dammit, another implicit rule
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
    elif rulename == 'soldiers':
        for soldier in rule:
            if 'soldierNames' not in soldier:
                # xcom-files has this
                return rule
            snames = []
            for sname in soldier['soldierNames']:
                if sname == 'delete':
                    snames = []
                else:
                    for fname in mod.findall(sname):
                        if fname.lower().endswith('.nam'):
                            snames.append(fname)
            soldier['soldierNames'] = snames
    elif rulename == 'terrains':
        for terrain in rule:
            if 'delete' in terrain:
                continue
            if 'mapBlocks' not in terrain:
                # wtf is a terrain w/o mapblocks?? aha, a merged one.
                # if so, do nothing. merge should just update-merge.
                continue
            terrain["mapFiles"] = []
            for mb in terrain['mapBlocks']:
                try:
                    terrain["mapFiles"].append({
                        "type": mb["name"],
                        "map": mod.findone("MAPS/" + mb["name"] + ".MAP"),
                        "rmp": mod.findone("ROUTES/" + mb["name"] + ".RMP")})
                except FileNotFoundError as e:
                    terrain["mapFiles"].append({
                        "type": mb["name"],
                        "map": None,
                        "rmp": None})
                    print(e)
            terrain["mapDataFiles"] = []
            for mds in terrain["mapDataSets"]:
                try:
                    terrain["mapDataFiles"].append({
                        "type" : mds,
                        "mcd": mod.findone("TERRAIN/" + mds + ".MCD"),
                        "pck": mod.findone("TERRAIN/" + mds + ".PCK"),
                        "tab": mod.findone("TERRAIN/" + mds + ".TAB")})
                except FileNotFoundError as e:
                    terrain["mapDataFiles"].append({
                        "type": mds,
                        "mcd": None,
                        "pck": None,
                        "tab": None})
                    print(e)
    elif rulename == 'extraSprites':
        for extrasprite in rule:
            esfiles = {}
            for idx, path in extrasprite['files'].items():
                # obscure crap about cobbling up a spritesheet from a dir
                expaths = mod.findall(path)
                if len(expaths) == 1:
                    expaths = expaths[0]
                esfiles[idx] = expaths
            extrasprite['files'] = esfiles
    return rule

""" A map of unique attribute names in mod yaml doc collections
    to the collections' names

    Special cases:
     - delete in soldiers::soldierNames (res ref)
            probably means the name set should be reset.
            handled in expand_paths()
     - extraStrings
            handled explicitly, since they require second-tier dict merge
     - extraSprites, extraSounds
            modIndex/modOffset shenanigans
     - extraSounds
            might be same as above, but not implemented
     - globe
            straight dict update
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

    'extraStrings': merge_extrastrings,
    'extraSprites': merge_extrasprites,
    'extraSounds': merge_extrasounds,

# None means no merge; replace entirely
    # OXgit Aug14
    'defeatScore': None,
    'defeatFunds': None,
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

    # load common and standard strings, merge them
    baseStrings = []
    commonStrings = []

    for fpath in mod.findall(os.path.join('Language', '*.yml')):
        fname = os.path.basename(fpath)
        translation = yamload(fpath)
        print("Loading strings from {}".format(fpath))
        for lang, strings in translation.items():
            es = {'type': lang, 'strings': strings}
            print("lang {} strings {} of {}".format(lang, type(strings), len(strings)))

        if 'common' in fpath.lower():
            baseStrings.append(es)
        else:
            commonStrings.append(es)

    extraStrings = merge_extrastrings(mod.index, baseStrings, commonStrings)

    return { 'extraSprites': surfaces, 'extraStrings': extraStrings, '_palettes': palettes }

def load(finder):
    present_mods = dict((mod.id, mod) for mod in [ ModMeta(p, finder) for p in finder.modlist ])
    """ Mod dependencies

        mod can have isMaster attribute . This displays it as a 'game type' in the options screen.
        the list below then displays only the mods that have the selected mod as the master.

        Engine/Options.cpp:585
            // add in any new mods picked up from the scan and ensure there is but a single
            // master active

        mod can have master attribute. this points to some other mod this mod is supposed to mod.
        so it must be loaded after all its dependency has been loaded.
        a master of '*' is equivalent to no master at all (Engine/ModInfo.cpp:61)

        Engine/Options.cpp:717
            // if this is a master but it has a master of its own, allow it to
            // chainload the "super" master, including its rulesets
            if (modInfo.isMaster() && !modInfo.getMaster().empty())

    """


    # gather all active mods into two sets. master mod is separate.
    active_mods = {}
    mastermod = None # active master. there can be only one.
    for modrec in finder.config['mods']:
        if modrec['active']:
            mod = present_mods[modrec['id']]
            # assert a single master
            if mod.isMaster:
                if mastermod is not None:
                    raise Exception("Two masters active: {} and {}".format(mastermod, mod))
                mastermod = mod
            active_mods[mod.id] = mod

    # link up the master mod with its master chain
    # parts might be inactive, so activate them.
    mm = mastermod
    while mm.masterID is not None:
        if not mm.isMaster:
            raise WTF
        active_mods[mm.masterID] = present_mods[mm.masterID]
        mm.master = present_mods[mm.masterID]
        mm = mm.master


    # link up with masters
    for mod in active_mods.values():
        if mod.masterID is not None:
            mod.master = active_mods[mod.masterID]

    # resolve dependencies into a load order
    load_order = []
    def find_least_dependent(active_mods, load_order):
        for mod in active_mods.values():
            if mod.master is None:
                return mod
            if mod.master in load_order:
                return mod
        raise Exception("RequiredMasterMissing: mod.master={} load_order=[{}]".format(
                            mod.masterID, ','.join(map(lambda x: x.id, load_order))))

    mod_index = 0
    while len(active_mods) > 0:
        mod = find_least_dependent(active_mods, load_order)
        load_order.append(mod)
        mod.index = mod_index
        mod_index += 1
        del active_mods[mod.id]

    ruleset = {}
    for mod in load_order:
        print("\nLoading '{}' name='{}' from '{}'".format(mod.id,  mod.name, mod.root))
        # the topmost master mod, one of xcom1 or xcom2 is:
        if mod.isMaster and mod.master is None:
            if mod.id not in ('xcom1', 'xcom2'):
                raise Exception("masterless master mod {}".format(mod))
            ruleset = load_vanilla(mod)
        yamdirload_and_merge(mod, ruleset, mod.root)
        rul_dir = os.path.join(mod.root, 'Ruleset')
        if os.path.isdir(rul_dir):
            yamdirload_and_merge(mod, ruleset, rul_dir)

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

def load_ruleset(path):
    """ load the ruleset from a self-contained installation and return it """
    userdir = os.path.join(path, 'user')
    finder = Finder(userdir, userdir, path)
    print(finder)
    return load(finder)

def main():
    finder = Finder(cfgdir, userdir, datadir)
    print(finder)
    ruleset = load_ruleset(sys.argv[1])

    ofname = 'ruleset.py' if len(sys.argv) < 3 else sys.argv[2]
    with open(ofname, "w") as f:
        f.write("ruleset = {\n ")
        f.write(pprint.pformat(ruleset, width=144)[1:])
        f.write(textwrap.dedent("""
            def get_trans(lang="{lang}", fallback = False):
                def find_lang(lname):
                    for ess in ruleset["extraStrings"]:
                        if ess['type'] == lname:
                            return ess['strings']
                    return {{}}

                trans = find_lang(lang)
                falltrans = find_lang("{fblang}")

                if fallback:
                    return lambda k : trans.get(k, falltrans.get(k, k))
                else:
                    return lambda k : trans.get(k, k)

            """.format(fblang = FALLBACK_LANG,
                         lang = finder.config['options'].get('language', FALLBACK_LANG))))

if __name__ == '__main__':
    main()
