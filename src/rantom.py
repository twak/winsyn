import random as r
import os
import sys
from src import utils, cgb
import json
from pathlib import Path

"""
RantomCache stores the parameters. Other fns here store, load, seed the parameters and their distributions.
"""


def reset():
    global RANDOM_CACHE_COUNT, ALL_CACHES, ROOT
    RANDOM_CACHE_COUNT = 0
    ALL_CACHES = []
    ROOT = RantomCache(0, name="root", parent=None)
    cgb.reset_rnd()

def seed(val):
    r.seed(val)
    # global ALL_CACHES, RANDOM_CACHE_COUNT
    # ALL_CACHES=[]
    # RANDOM_CACHE_COUNT = 0

def write_std(header="", simple=True):
    write (sys.stdout, header, simple)

def write_file(path, header=""):
    os.makedirs (Path(path).parent, exist_ok=True )
    handle = open (path, 'w')
    write (handle, header)
    handle.close()

def write (handle, header=""):

    keys = {}

    for rc in ALL_CACHES:
        for k, v in rc.rantom_keys_dict.items():
            keys[f"{rc.name}/{k}"] = v

    json.dump(keys, handle, indent=2)

def set_param_override(param_override):
    global PARAM_OVERRIDE
    PARAM_OVERRIDE = param_override

def read_params(f):

    with open(f, 'r') as fp:
        return json.load(fp)

def dump_all():

    for rc in ALL_CACHES:
        for k, v in rc.rantom_keys_dict.items():
            print(f'{k}  ({v})')

class RantomCache():

    def __init__(self, failure_rate = 0, name=None, parent="x") -> None:
        self.r = failure_rate
        self.rantom_keys_dict = {}
        global ROOT
        self.parent = ROOT if parent == "x" else parent

        global RANDOM_CACHE_COUNT, ALL_CACHES
        self.name = name if name else f"random_cache_{RANDOM_CACHE_COUNT}"
        RANDOM_CACHE_COUNT += 1
        ALL_CACHES.append(self)

        # if we have been given parameters (from a file or the ui) patch them in here.
        global PARAM_OVERRIDE
        for k, v in PARAM_OVERRIDE.items():
            if k.startswith(self.name+"/"):
                self.rantom_keys_dict[k.replace(self.name+"/", "")] = v

    def lookup(self, key, key_desc, dist_desc, value, lookup=True):

        if key == "?":
            print("warning: undefined rantom variable here")

        if key!="?" and key in self.rantom_keys_dict: # we've seen this key before, return the same value
            return self.rantom_keys_dict[key]
        else:
            if lookup and self.parent is not None:

                pc = r.random() # we only store the outcome, not the process

                if pc < self.r: # not failure
                    value = self.parent.lookup (key, key_desc, dist_desc, value) # sample from the parent
                # else we fail and use the local value

            self.rantom_keys_dict[key] = value

        return value


    def random(self, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, "float \in {0,1}", r.random(), lookup=lookup )

    def randrange(self, end, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, f"integer \in {{0,{end}}}", 0 if end == 0 else r.randrange(end), lookup=lookup )

    def gauss(self, m, s, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, f"float \in gauss \mu={m} \sigma = {s}", r.gauss(m,s), lookup=lookup )

    def gauss_clamped(self, m, s, low, high, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, f"float \in gauss \mu={m} \sigma = {s}", utils.clamp(r.gauss(m,s), low, high), lookup=lookup )

    def uniform(self, a, b, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, f"float \in {{{a},{b}}}", r.uniform(a,b), lookup=lookup )

    def uniform_mostly(self, chance, value, a, b, key="?", desc="?", lookup=True):

        if r.random() < chance:
            out = value
        else:
            out = r.uniform(a, b)

        return self.lookup ( key, desc, f"uniform mostly. {value} with chance {chance} otherwise float \in {a} to {b}", out, lookup=lookup )

    def weighted_int(self, l, key="?", desc="?", lookup=True):

        c = r.randrange(sum(l))

        x = 0
        vvalue = 0 # fallback

        for i, v in enumerate(l):
            x += v
            if x > c:
                vvalue = i
                break

        return self.lookup(key, desc, f"weighted select in {', '.join(map(str,l))}", vvalue, lookup=lookup)

    def choice(self, l, key="?", desc="?", lookup=True):

        l = l if isinstance(l, list) else list(l)
        end = len(l)
        i = min ( end-1, self.lookup ( key, desc, f"choice \in {{0,{end}}}", r.randrange(end) ) )

        return l[i]

    def other (self, lamb, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, "other", lamb(), lookup=lookup )

    def value (self, value, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, "other", value, lookup=lookup )

    def store(self, key, value, desc="?", lookup=True):
        key = "_" + key
        self.rantom_keys_dict[key] = value

    def store_v(self, key, value, desc="?", lookup=True):

        for v, x in zip (value, ["x","y","z"]):
            k = f"_{key}_{x}"
            self.rantom_keys_dict[k] = v

    def __hash__(self):
        return hash((self.name))

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.name == other.name
        return False


def random(key="?", desc="?"):
    return ROOT.random(key, desc)

def randrange(end, key="?", desc="?"):        
    return ROOT.randrange(end, key, desc)

def uniform(a, b, key="?", desc="?"):
    return ROOT.uniform(a, b, key, desc)

def gauss(m, s, key="?", desc="?"):
    return ROOT.gauss(m, s, key, desc)

def gauss_clamped(m, s, low, high, key="?", desc="?"):
    return ROOT.gauss_clamped(m, s, low, high, key, desc)

def uniform_mostly(chance, value, a, b, key="?", desc="?"):
    return ROOT.uniform_mostly(chance, value, a, b, key, desc)

def weighted_int(l, key="?", desc="?"):
    return ROOT.weighted_int(l, key, desc)

def choice(l, key="?", desc="?"):
    return ROOT.choice(l, key, desc)

def other (lamb, key="?", desc="?"):
    return ROOT.other(lamb, key, desc)

def value (value, key="?", desc="?"):
    return ROOT.other(value, key, desc)

def store ( key, value, desc="?" ):
    return ROOT.store ( key, value, desc )

def store_v ( key, value, desc="?" ):
    return ROOT.store_v ( key, value, desc )


PARAM_OVERRIDE={}
RANDOM_CACHE_COUNT = 0
ALL_CACHES = []
ROOT = RantomCache(0, name="root", parent=None)