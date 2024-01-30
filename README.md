
# setting up

We use [Blender 3.3](https://ftp.nluug.nl/pub/graphics/blender//release/Blender3.3/). Later versions may work too.

# resource files

The `config.py` file defines `resource_path` which should be the location of the resources folder.

The model requires a resources files with various textures and meshes from different sources. We include a single example resource of each type in the XXXX folder - these are enough to run the model, but do not have much diversity. Running the model with only these resources will not match our results!

* The 3D clutter scenes can be downloaded from the [KAUST datastore](). They should be added added to the `exterior_clutter` folder. 

* The script `util/import_google_panos.py` can be used to download the panoramas used for the published dataset. It takes a single argument: your resource folder, and downloads images here in the subfolder `outside`.
** Alternately, download a [different set of panoramas from google directly](https://sites.google.com/view/streetlearn/dataset).

* Signs can be downloaded from the [Kaust datastore](https://repository.kaust.edu.sa/handle/10754/686575). They should be in the `signs` folder of your resource folder. The downloaded and unzipped files can be split into folders `large`, `medium`, and `small` using the script `utils/split_signs.py`.

** Rename and move the signs using the script `import.signs.py`. It takes two arguments - the root folder of the unzipped signs dataset and the resource folder.

* If you wish to generate the variant with many textures, download and unzip the [dtd](https://www.robots.ox.ac.uk/~vgg/data/dtd/) dataset into the `dtd` folder inside your resource folder.

* The interior textures are from matterport. 
** You can download them by following the instructions (involving sending them a form and getting a [download script](https://github.com/jlin816/dynalang/blob/0da77173ee4aeb975bd8a65c76ddb187fde8de81/scripts/download_mp.py#L4))
** Run the script thusly to download all the interior panoramas:
```
download_mp.py /a/location --type matterport_skybox_images 
```
** extract and convert the downloaded skyboxes into the panoramic image format using the script `util/import_matterport.py`. It takes two arguments: the root of the downloaded panoramas and your resource folder.

# running from within Blender

Open the `winsyn.blend` file in Blender 3.3. Then grab a text pane in blender, open the `go.py` script, and run it. Debugging requires a more challenging setup, I used something like [this](https://code.blender.org/2015/10/debugging-python-code-with-pycharm/) combined with the commented out `pydevd_pycharm.settrace` lines in `go.py`.

# running on a cluster

I deploy on our ibex/slurm cluster to render entire datasets. I use the [nytimes](https://github.com/nytimes/rd-blender-docker?tab=readme-ov-file#331) Blender docker image built as singularity container and a job script like so. Note the fixed locations for the resources and output folders, specified in the `config.py` file. `output_dataset` is the output dataset name. On ibex I rendered on the p100 and v100 nodes.

```
echo "Welcome to Windows"
outdir="/ibex/wherever/you/want/output_dataset"
mkdir -p $outdir

while :
do
  SINGULARITYENV_WINDOWZ_STYLE="$1" singularity exec --nv --bind $outdir:/home/twak/data/dataset_out --bind /ibex/wherever/you/put/resources:/home/twak/data/panos --bind /ibex/wherever/you/put/code/:/home/twak/code/windowz  /ibex/wherever/you/put//blender_3_3.sif blender -b /ibex/wherever/you/put/windowz/winsyn.blend --python /ibex/wherever/you/put/windowz/src/go.py -- --cycles-device OPTIX
  echo "blender crashed. let's try that again..."
done
```

I keep a separate `config.py` on my local machine and server with different resource locations.

# variations

These are known as 'styles' in the code and change the behavior of the model (e.g., all-grey walls, or all-nighttime lighting). They are set in the config.py file or using the `WINDOWZ_STYLE` env variable. The sequences below render the variations for various sequences of paramters and create the labels where required.

* `rgb;labels` the default baseline model (and also render the labels).
* `rgb;128nwall;64nwall;32nwall;16nwall;8nwall;4nwall;2nwall;1nwall;labels` changes the number of wall materials
*  `0monomat;0.33monomat;0.66monomat;1monomat;2monomat;4monomat;0multimat;0.33multimat;0.66multimat;1multimat;2multimat;4multimat;labels;all_brick` changes the parameterization of the procedural materials. monomat is a single proc material for each object class. multi-mat is the baseline number of materials. The numbers are multipliers on the deviations for parameter generation.
*  `nosplitz;nosplitz_labels;mono_profile;mono_profile_labels;only_rectangles;only_rectangles_labels;no_rectangles;no_rectangles_labels;only_squares;only_squares_labels;single_window;single_windows_labels;wide_windows;wide_windows_labels` the window-shape parameterization variation.
* `lvl9;lvl8;lvl7;lvl6;lvl5;lvl4;lvl3;lvl2;lvl1;lvl9_labels;lvl8_labels;lvl7_labels;lvl6_labels;lvl5_labels;lvl4_labels;lvl3_labels;lvl2_labels;lvl1_labels` these are the number of modeled labels (i.e., just starting will the `wall` label with `lvl1`.
*`0cen;3cen;6cen;12cen;24cen;48cen;96cen;labels;0cenlab;3cenlab;6cenlab;12cenlab;24cenlab;48cenlab;96cenlab` these are the camera positions (over a circle).
* `1spp;2spp;4spp;8spp;16spp;32spp;64spp;128spp;256spp;512spp;nightonly;dayonly;notransmission;0cen;3cen;6cen;12cen;24cen;48cen;nosun;nobounce;fixedsun;monomat;labels;0cenlab;3cenlab;6cenlab;12cenlab;24cenlab;48cenlab` these are the rendering samples per pixel.
* `canonical;64ms;128ms;256ms;512ms;1024ms;2048ms;labels;edges;diffuse;normals;col_per_obj;texture_rot;voronoi_chaos,phong_diffuse` these are the many varied materials experiments.

# labels

The labels

# parameters

The model writes out an attribute file to the `attribs` directory containing all the parameters used to generate a given scene. There are a variable number of these (sometimes thousands), and not all are human-friendly. The file also contains assorted metadata including the random seed and render times.

You can vary the model's output by changing the parameters. By default a random seed is created and used to generate the remainder of the parameters. There is no complete description of the paramters, but the code samples them from the `RantomCache` class in `rantom.py`:

```
r2.uniform(0.1, 0.22, "stucco_crack_size", "Size of stucco cracks")
```

After a parameter name has been assigned (`"stucco_crack_size"`), asking for it again in the code will return the same value (even if it lies outside of the given distribution).

If you generate the same scene from the same random seed, it should always generate the same scene (on a single machine). However, small changes in the code path will change this, so it is also possible to pass in a paramter file containing all of these. Any parameters you do not list will be generated randomly as normal.

# code overview

* `go.py` start reading here - the main loop (`for step in range (config.render_number):`) runs until all renders have completed.
* 






















