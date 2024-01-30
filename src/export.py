import bpy
import os


def prep_scene_obj():

    objs = bpy.context.scene.objects
    objs.remove(objs["interior"], do_unlink=True)
    objs.remove(objs["canyon"], do_unlink=True)

    


def bake_all(destinationPath = "C:\\Users\\twak\\Downloads\\exports\\", resolution=128):

    prep_scene_obj()
    bpy.ops.object.select_all(action='DESELECT')

    for obj in  bpy.context.view_layer.objects:
        
        if obj.type == 'MESH':

            # set selection
            bpy.context.view_layer.objects.active = obj    
            obj.select_set(True)

            if obj.hide_get() or obj.hide_viewport:
                obj.hide_set(False) # can't select  hidden
                obj.select_set(True) # select to delete
                res = bpy.ops.object.delete()
            else:
                bake_selected(destinationPath, resolution)    
            
                obj.select_set(False)

        elif obj.type == 'CURVE':

            obj.hide_set(False)
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            res = bpy.ops.object.delete()
            print (f" >>>> {res}")

    bpy.ops.export_scene.obj(filepath=destinationPath + 'mesh.obj')
    

def bake_selected(destinationPath, resolution=2048, specular=0.2): # https://github.com/davidmoncas/BakeBlenderTextures/blob/main/bake_and_export.py#L51

    b=bpy.ops 
    c=bpy.context 

    # Create the destination folder
    if not os.path.exists(destinationPath):
        os.mkdir(destinationPath) 


    # Check the selected object
    selected_objects = bpy.context.selected_objects

    if len(selected_objects) == 0 :
        print("please select the object")
        return
        
    elif len(selected_objects) > 1:
        print ("select exactly one object")
        return
    else:
        M = selected_objects[0]
    
    # Create a new UV map
    print("creating a new UV map")
    b.mesh.uv_texture_add()
    M.data.uv_layers.active_index = 1
    M.data.uv_layers[-1].name = "baked"

    # Unwrap the 3d model
    print("unwraping the model")
    b.object.editmode_toggle()
    b.uv.smart_project(scale_to_bounds=True)
    b.object.editmode_toggle()


    def bb(channel):
        # Create a new image
        print(f"creating a new image for {channel}")
        texture = bpy.data.images.new(f'tex_{channel}_{M.name}', resolution, resolution)
        # bpy.

        #b.image.new(name="texture", width=resolution, height=resolution, color=(0.0, 0.0, 0.0, 1.0), alpha=False, generated_type='BLANK', float=False, use_stereo_3d=False)

        #Change the materials with the node editor
        print(f"copying the texture in each node {channel}")
        for material in M.material_slots:
            
            print("working in: " + material.name) 
            material.material.use_nodes=True
            newNode=material.material.node_tree.nodes.new("ShaderNodeTexImage")
            newNode.image=texture
        
        #Deselect all the nodes except for the new one
            for node in material.material.node_tree.nodes:
                node.select=False
            
            newNode.select = True
            material.material.node_tree.nodes.active = newNode
            
        # Switch to Cycles
        c.scene.render.engine = 'CYCLES'

        # Starting the bake
        print(f"Baking... @ {resolution}")
        bpy.ops.object.bake(type=channel, pass_filter={"COLOR"},use_selected_to_active = False, margin = 3, use_clear = True)
        print("finished")

        #Saving the image in the desired folder
        print("saving texture image")
        texture.filepath_raw = destinationPath + f"map_{M.name}_{channel}.png"
        texture.file_format = 'PNG'
        texture.save()
        print("image saved")

        return texture

    diffuse_image = bb("DIFFUSE")
    normal_image  = bb("NORMAL")
    rough_image  = bb("ROUGHNESS")

    # switching to the new UV Map
    c.view_layer.objects.active = M
    M.data.uv_layers["baked"].active_render = True
    M.data.uv_layers.active_index=0
    b.mesh.uv_texture_remove()


    # Removing all the previous materials
    for x in M.material_slots: #For all of the materials in the selected object:
        bpy.context.object.active_material_index = 0 #select the top material
        bpy.ops.object.material_slot_remove() #delete it

    # Create a new material
    mat=bpy.data.materials.new(f"baked_tex_mat_{M.name}")
    mat.use_nodes=True

    node_tree = mat.node_tree

    diffuse_node = node_tree.nodes.new("ShaderNodeTexImage")
    # diffuse_node.select = True
    # node_tree.nodes.active = diffuse_node
    diffuse_node.image=diffuse_image

    bsdf_node=node_tree.nodes['Principled BSDF']
    node_tree.links.new(diffuse_node.outputs["Color"], bsdf_node.inputs["Base Color"])

    rough_node = node_tree.nodes.new("ShaderNodeTexImage")
    rough_node.image=rough_image
    node_tree.links.new(rough_node.outputs["Color"], bsdf_node.inputs["Roughness"])

    normal_node = node_tree.nodes.new("ShaderNodeTexImage")
    normal_node.image=normal_image

    normal_map_node =  node_tree.nodes.new("ShaderNodeNormalMap")

    node_tree.links.new(normal_node.outputs["Color"], normal_map_node.inputs["Color"])
    node_tree.links.new(normal_map_node.outputs["Normal"], bsdf_node.inputs["Normal"])

    bsdf_node.inputs["Specular"].default_value = specular

    M.data.materials.append(mat)


