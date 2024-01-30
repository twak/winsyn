import os, time, pathlib
from os.path import expanduser

samples = 256 # default render samples
ortho = False # orthographic camera

jobid = int ( os.environ.get("SLURM_JOB_ID", int(time.time()))) # used to make unique-per-node temporary folders
print(f"running under jid {jobid}") # unique per node.

physics = True

# todo: these should match your resource and render locatinos
resource_path = pathlib.Path(__file__).parent.parent.resolve().joinpath("resources")  # download resources as in readme.md; example format in `resource_demo` folder.
render_path = os.path.join (expanduser("~"), "winsyn_renders")

if True: # toggle this to run interactively in blender / use the headless codepath
    interactive=True
else:
    render_number= 2
    interactive=False

    # which variations to render. This may be overwritten with the WINDOWZ_STYLE env parameter.
    # these are order sensitive as they emulate a build/set-regular-materials/render color/set-label-materials/render-labels session in Blender
    style="rgb;labels"

    # _h styles: wall material counts
    # style="rgb;128nwall;64nwall;32nwall;16nwall;8nwall;4nwall;2nwall;1nwall;labels"

    # _g styles: procedural material variations
    # style="all_brick"
    # style="0monomat;0.33monomat;0.66monomat;1monomat;2monomat;4monomat;0multimat;0.33multimat;0.66multimat;1multimat;2multimat;4multimat;labels;all_brick"

    # _f styles: window geometry variations
    # style="nosplitz;nosplitz_labels;mono_profile;mono_profile_labels;only_rectangles;only_rectangles_labels;no_rectangles;no_rectangles_labels;only_squares;only_squares_labels;single_window;single_windows_labels;wide_windows;wide_windows_labels"

    # _e styles: which labels are modelsd
    # style="lvl9;lvl8;lvl7;lvl6;lvl5;lvl4;lvl3;lvl2;lvl1;lvl9_labels;lvl8_labels;lvl7_labels;lvl6_labels;lvl5_labels;lvl4_labels;lvl3_labels;lvl2_labels;lvl1_labels"

    # _d3 styles: camera positions
    # style="0cen;3cen;6cen;12cen;24cen;48cen;96cen;labels;0cenlab;3cenlab;6cenlab;12cenlab;24cenlab;48cenlab;96cenlab"

    # _d styles: samples per pixel + some lighting
    #style = '1spp;2spp;4spp;8spp;16spp;32spp;64spp;128spp;256spp;512spp;nightonly;dayonly;notransmission;0cen;3cen;6cen;12cen;24cen;48cen;nosun;nobounce;fixedsun;monomat;labels;0cenlab;3cenlab;6cenlab;12cenlab;24cenlab;48cenlab'

    # _c styles: different materials + render durations.
    #style = "canonical;64ms;128ms;256ms;512ms;1024ms;2048ms;labels;edges;diffuse;normals;col_per_obj;texture_rot;voronoi_chaos,phong_diffuse"
