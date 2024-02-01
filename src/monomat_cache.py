import math
import random as r

from src import utils
from src.rantom import RantomCache

"""
A paramater set for exploring material distributions (nmat)
"""

class MonoMatCache(RantomCache):

    def __init__(self,  name=None, sigma=0, monomat=False) -> None:

        self.name = name if name else f"mock cache"
        self.monomat = monomat
        self.sigma=sigma # 0...1 should interpolate between 0 variation and "full" model variation

    def lookup(self, key, key_desc, dist_desc, value, lookup=True):
        return value

    def random(self, key="?", desc="?", lookup=True):

        return self.lookup ( key, desc, "float \in {0,1}", 0.5 + (super.random(key,desc)*0.5) * self.sigma , lookup=lookup )

    def randrange(self, end, key="?", desc="?", lookup=True):

        v = r.uniform(math.floor(end/2 - self.sigma * end), math.ceil(end/2 + self.sigma * end))

        return self.lookup ( key, desc, f"integer \in {{0,{end}}}", utils.clamp( int(v), 0, end-1), lookup=lookup )

    def gauss(self, m, s, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, f"float \in gauss \mu={m} \sigma = {s}", r.gauss(m,s) * self.sigma, lookup=lookup )

    def gauss_clamped(self, m, s, low, high, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, f"float \in gauss \mu={m} \sigma = {s}", utils.clamp(r.gauss(m,s) * self.sigma, low, high), lookup=lookup )

    def uniform(self, a, b, key="?", desc="?", lookup=True):

        if key.startswith("interior_brightness"):
            return 0.5

        if key == "brick_random_seed":
            return r.uniform(0,10000)

        range2 = (b - a) / 2
        mid = range2 + a

        return self.lookup ( key, desc, f"float \in {{{a},{b}}}",
                             r.uniform(mid - range2*self.sigma, mid + range2 * self.sigma),
                             lookup=lookup )

    def uniform_mostly(self, chance, value, a, b, key="?", desc="?", lookup=True):

        if r.uniform(0.5-self.sigma, 0.5+self.sigma) < chance:
            return value

        range2 = (b - a) / 2
        mid = range2 + a

        return self.lookup ( key, desc, f"uniform mostly. {value} with chance {chance} otherwise float \in {a} to {b}",
                             r.uniform(mid - range2*self.sigma, mid + range2 * self.sigma), lookup=lookup )

    def weighted_int(self, l, key="?", desc="?", lookup=True):

        if self.monomat:

            if key == "timber_frame_material":
                return 0 # stucco timber frames

            if key.startswith("ext_wall_mat_choice"):
                return 1 # brick

            if key.startswith("int_wall_mat_choice"):
                return 0

            if key.startswith("glass_type_choice_"):
                return 2 # clear glass

            if key.startswith("metal_color_distribution"):
                return 0 # metalic grey metal

            if key == "frame_mat_choice":
                return 0 # wooden frames

            if key.startswith("surround_material_choice"):
                return 2 # wooden

            if key == "blinds_mat_type":
                return 1

            if key == "blinds_frame_mat":
                return 0

            if key == "balcony_mat_type":
                return 0

            if key == "balcony_glass_type":
                return 0

            if key == "balcony_hold_is_wood":
                return 1

            if key == "balcony_base_mat_choice":
                return 0

            if key == "balcony_pillar_mat_choice":
                return 2

            if key == "merge_win_side":
                return 1 # use wall for win-sides.

            if key == "pipe_material":
                return 0

            if key == "wire_material":
                return 0

        if self.sigma == 0:
            vvalue = 0
        else:
            c = r.randrange(math.ceil( sum(l) * min(1,self.sigma )) )

            x = 0
            vvalue = 0 # fallback

            for i, v in enumerate(l):
                x += v
                if x > c:
                    vvalue = i
                    break

        return self.lookup(key, desc, f"weighted select in {', '.join(map(str,l))}", vvalue, lookup=lookup)

    def choice(self, l, key="?", desc="?", lookup=True):

        v = r.uniform(0, math.ceil(min(1,self.sigma) * len(l)))
        return self.lookup(key, desc, f"choice", l[int(v)], lookup=lookup)

        return l[0]

    def other (self, lamb, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, "other", lamb(), lookup=lookup )

    def value (self, value, key="?", desc="?", lookup=True):
        return self.lookup ( key, desc, "other", value, lookup=lookup )

    def __hash__(self):
        return hash((self.name))

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.name == other.name
        return False
