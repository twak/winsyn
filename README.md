# WinSyn Synthetic Procedural Model

WinSyn is a research project to provide a matched pair of synthetic and real images for machine learning tasks such as segmentation. You can read the [paper](https://arxiv.org/abs/2310.08471) online.

<img src='https://github.com/twak/winsyn/blob/main/winsyn.jpg' width='300'>

This repository contains code for running the synthetic procedural model. We also created matching photos of [75k real windows](https://github.com/twak/winsyn_metadata).

### setting up

We use [Blender 3.3](https://ftp.nluug.nl/pub/graphics/blender//release/Blender3.3/). Open the [`winsyn.blend`](https://github.com/twak/winsyn/blob/main/winsyn.blend) file in blender and run the [`go.py`](https://github.com/twak/winsyn/blob/main/src/go.py) script to run in interactive mode.

### resource files

The model requires a resources files with various textures and meshes from different sources. We include a [single example](https://github.com/twak/winsyn/tree/main/resources) resource of each type - these are enough to run the code, but do not have much diversity. Running the model with only these resources will not match our results... The [`config.py`](https://github.com/twak/winsyn/blob/main/src/config.py) file defines `resource_path` which should be the location of the resources folder.

* The 3D clutter scenes can be downloaded from the [KAUST datastore](https://doi.org/10.25781/KAUST-5E9C0). They should be added added to the `exterior_clutter` folder. 

* The script [`import_google_panos.py`](https://github.com/twak/winsyn/blob/main/import/import_google_panos.py) can be used to download the panoramas used for the published dataset. It takes a single argument: your resource folder, and downloads images here in the subfolder `outside`.
  - Alternately, download a [different set of panoramas from google directly](https://sites.google.com/view/streetlearn/dataset).

* Signs can be downloaded from the [Kaust datastore](https://repository.kaust.edu.sa/handle/10754/686575). They should be in the `signs` folder of your resource folder. The downloaded and unzipped files can be split into folders `large`, `medium`, and `small` using the script [`split_signs.py`](https://github.com/twak/winsyn/blob/main/import/import_signs.py). It takes two arguments - the root folder of the unzipped signs dataset and the resource folder.

* The interior textures are from matterport. 
  * You can download them by following the instructions (involving sending them a form and getting a [download script](https://github.com/jlin816/dynalang/blob/0da77173ee4aeb975bd8a65c76ddb187fde8de81/scripts/download_mp.py#L4))
  * Run the script thusly to download all the interior panoramas:
  ```
  download_mp.py /a/location --type matterport_skybox_images 
  ```
 * extract and convert the downloaded skyboxes into the panoramic image format using the script [`import_matterport.py`](https://github.com/twak/winsyn/blob/main/import/import_matterport.py). It takes two arguments: the root of the downloaded panoramas and your resource folder.

* If you wish to generate the variant with many textures (`texture_rot`), download and unzip the [dtd](https://www.robots.ox.ac.uk/~vgg/data/dtd/) dataset into the `dtd` folder inside your resource folder.

### running from within Blender

* Set the `resource_path` in [config.py](https://github.com/twak/winsyn/blob/main/src/config.py#L13) to where you downloaded the resource files
* Open the `winsyn.blend` file in Blender 3.3. 
* Open a text pane in blender with the [`go.py`](https://github.com/twak/winsyn/blob/main/src/go.py) script
* Run the script! Generation time varies from 20 sections to a few minutes. Blender hangs during generation. Some generation may take a very long time depending on the parameters selected.
* Debugging requires a more challenging setup, I use Pycharm with something like [this](https://code.blender.org/2015/10/debugging-python-code-with-pycharm/) combined with the commented out [`pydevd_pycharm.settrace`](https://github.com/twak/winsyn/blob/main/src/go.py#L66) lines in `go.py`. The workflow goes something like - edit code in pycharm, switch to blender to run, switch back to pycharm to set breakpoints/inspect elements.

### running headless

* as well as `resource_path` as above...
* set the `render_path` in [config.py](https://github.com/twak/winsyn/blob/main/src/config.py#L14) to the location where renders should be written
* set the number of renders you want in `render_number`.
* set `interactive` to False in [config.py](https://github.com/twak/winsyn/blob/main/src/config.py#L16).
* optional: set the `style` (variations) in `config.py`
* run with something like (the CUDA bit says to use an Nvidia GPU to accelerate rendering):

```
blender -b /path/to/winsyn/wall.blend --python /path/to/winsyn/src/go.py -- --cycles-device CUDA
```

### running on a cluster

I deploy on our [ibex](https://www.hpc.kaust.edu.sa/ibex)/slurm cluster to render large datasets. I use the [nytimes](https://github.com/nytimes/rd-blender-docker?tab=readme-ov-file#331) Blender docker image built as singularity container ([singularity definition file](https://github.com/twak/winsyn/blob/main/import/Singularity.def)) and a job script similar to the below. On ibex I rendered on the p100 and v100 nodes, and run about 10 machines to render 2k images overnight.

with a `run.sh` script:
```
echo "Welcome to Windows"
outdir="/ibex/wherever/you/want/output_dataset"
mkdir -p $outdir
style="rgb;labels"

while : # "robustness"
do
  SINGULARITYENV_WINDOWZ_STYLE="$1" singularity exec --nv --bind $outdir:/container/winsyn/output --bind /ibex/winsyn/resources:/container/winsyn/resources --bind /ibex/winsyn:/container/winsyn /ibex/wherever/you/put//blender_3_3.sif blender -b /container/winsyn/winsyn.blend --python /container/winsyn/src/go.py -- --cycles-device OPTIX
  echo "blender crashed. let's try that again..."
done
```
with `config.py` lines `render_path=/container/winsyn/output` and `resource_path=/container/winsyn/resources`.

### variations

These are known as 'styles' in the code and change the behavior of the model (e.g., all-grey walls, or all-nighttime lighting - see the end of the paper's appendix for examples). They are defined in the `config.py` file or using the `WINDOWZ_STYLE` env variable. The sequences below render the variations for various sequences of paramters and create the labels where required.

* `rgb;labels` the default baseline model (and also render the labels).
* `rgb;128nwall;64nwall;32nwall;16nwall;8nwall;4nwall;2nwall;1nwall;labels` changes the number of wall materials
*  `0monomat;0.33monomat;0.66monomat;1monomat;2monomat;4monomat;0multimat;0.33multimat;0.66multimat;1multimat;2multimat;4multimat;labels;all_brick` changes the parameterization of the procedural materials. monomat is a single proc material for each object class. multi-mat is the baseline number of materials. The numbers are multipliers on the deviations for parameter generation.
*  `nosplitz;nosplitz_labels;mono_profile;mono_profile_labels;only_rectangles;only_rectangles_labels;no_rectangles;no_rectangles_labels;only_squares;only_squares_labels;single_window;single_windows_labels;wide_windows;wide_windows_labels` the window-shape parameterization variation.
* `lvl9;lvl8;lvl7;lvl6;lvl5;lvl4;lvl3;lvl2;lvl1;lvl9_labels;lvl8_labels;lvl7_labels;lvl6_labels;lvl5_labels;lvl4_labels;lvl3_labels;lvl2_labels;lvl1_labels` these are the number of modeled labels (i.e., just starting will the `wall` label with `lvl1`.
*`0cen;3cen;6cen;12cen;24cen;48cen;96cen;labels;0cenlab;3cenlab;6cenlab;12cenlab;24cenlab;48cenlab;96cenlab` these are the camera positions (over a circle).
* `1spp;2spp;4spp;8spp;16spp;32spp;64spp;128spp;256spp;512spp;nightonly;dayonly;notransmission;0cen;3cen;6cen;12cen;24cen;48cen;nosun;nobounce;fixedsun;monomat;labels;0cenlab;3cenlab;6cenlab;12cenlab;24cenlab;48cenlab` these are the rendering samples per pixel.
* `canonical;64ms;128ms;256ms;512ms;1024ms;2048ms;labels;edges;diffuse;normals;col_per_obj;texture_rot;voronoi_chaos,phong_diffuse` these are the many varied materials experiments.

### parameters

The model writes out an attribute file to the `attribs` directory containing all the parameters used to generate a given scene. There are a variable number of these (sometimes thousands), and not all are human-friendly. The file also contains assorted metadata including the random seed and render times.

You can vary the model's output by changing the parameters. By default a random seed is created and used to generate the remainder of the parameters. There is no complete description of the paramters, but the code samples them from the `RantomCache` class in `rantom.py`:

```
r2.uniform(0.1, 0.22, "stucco_crack_size", "Size of stucco cracks")
```

After a parameter name has been assigned (`"stucco_crack_size"`), asking for it again in the code will return the same value (even if it lies outside of the given distribution).

If you generate the same scene from the same random seed, it should always generate the same scene (on a single machine). However, small changes in the code path will change this, so consider creating a parameter list as below.

### todo lists and parameter lists

There is a [mechanism](https://github.com/twak/winsyn/blob/main/src/go.py#L90) to render a list of images using fixed seeds/parameters in headless/non-interactive mode. If there is a `todo.txt` file in the `config.render_path`, the system will try to render for each random seed (e.g., a number) in the file. One number per line. There is a robustness mechanism for multi-node rendering, but I have observed failures and had to run manulaly.

In addition, if there is an existing parameter (attribs) file for that seed (i.e., the file `render_path/attribs/random_seed.txt` exists), those parameters will override the random values that would otherwise be used. Attributes that are required but not specified in this file are sampled as usual.

### code overview

* `go.py` start reading here - the main loop (`for step in range (config.render_number):`) runs until all renders have completed.
* `config.py` contains the per-setup (for me this is laptop/desktop/cluster) configuration
* `rantom.py` contains the paramter-sampling and storage code
* `cgb.py` my CGAShape implementation. Very different extensions and limitations to other implementations :/
* `cgb_building.py` the main entry point for actual geometry generation. Uses CGA to create a basic building
* `cgb_*.py` the other major components which use CGA-list constructions
* `materials.py` this (horrible code monolith) is responsible for adding materials to the scene's geometry, as well as all variations. `pre_render` and `post_render` are the most interesting, with `go` as the entrypoint for the main texturing routine.
* `shape.py` and `subframe.py` create bezier shaped windows and then add geometry to them
