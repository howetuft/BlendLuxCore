from ..bin import pyluxcore
from .. import utils
from ..nodes.output import get_active_output


GLOBAL_FALLBACK_MAT = "__CLAY__"


def convert(material, scene):
    try:
        if material is None:
            return fallback()

        # print("converting material:", material.name)
        props = pyluxcore.Properties()
        luxcore_name = utils.get_unique_luxcore_name(material)

        node_tree = material.luxcore.node_tree
        if node_tree is None:
            msg = 'Material "%s": Missing node tree' % material.name
            scene.luxcore.errorlog.add_warning(msg)
            return fallback(luxcore_name)

        active_output = get_active_output(node_tree)

        if active_output is None:
            msg = 'Node tree "%s": Missing active output node' % node_tree.name
            scene.luxcore.errorlog.add_warning(msg)
            return fallback(luxcore_name)

        # Now export the material node tree, starting at the output node
        active_output.export(props, luxcore_name)

        return luxcore_name, props
    except Exception as error:
        msg = 'Material "%s": %s' % (material.name, error)
        scene.luxcore.errorlog.add_warning(msg)
        import traceback
        traceback.print_exc()
        return fallback()


def fallback(luxcore_name=GLOBAL_FALLBACK_MAT):
    props = pyluxcore.Properties()
    props.SetFromString("""
# The slight offset is there to avoid floating point precision issues
# with objects that are exactly at world center, e.g. "cube on a plane scene"

# Dark subgrid (10cm blocks)
scene.textures.__grid_10cm_1.type = "checkerboard3d"
scene.textures.__grid_10cm_1.texture1 = 0.4 0.4 0.4
scene.textures.__grid_10cm_1.texture2 = 0.3 0.3 0.3
scene.textures.__grid_10cm_1.mapping.type = "globalmapping3d"
scene.textures.__grid_10cm_1.mapping.transformation = 10 0 0 0 0 10 0 0 0 0 10 0 0.001 0.001 0.001 1

# Light subgrid (10cm blocks)
scene.textures.__grid_10cm_2.type = "checkerboard3d"
scene.textures.__grid_10cm_2.texture1 = 0.4 0.4 0.4
scene.textures.__grid_10cm_2.texture2 = 0.5 0.5 0.5
scene.textures.__grid_10cm_2.mapping.type = "globalmapping3d"
scene.textures.__grid_10cm_2.mapping.transformation = 10 0 0 0 0 10 0 0 0 0 10 0 0.001 0.001 0.001 1

# Big grid (1m blocks)
scene.textures.__grid_1m.type = "checkerboard3d"
scene.textures.__grid_1m.texture1 = "__grid_10cm_1"
scene.textures.__grid_1m.texture2 = "__grid_10cm_2"
scene.textures.__grid_1m.mapping.type = "globalmapping3d"
scene.textures.__grid_1m.mapping.transformation = 1 0 0 0 0 1 0 0 0 0 1 0 0.001 0.001 0.001 1

# Material
scene.materials.{mat_name}.type = "matte"
scene.materials.{mat_name}.kd = __grid_1m
    """.format(mat_name=luxcore_name))
    return luxcore_name, props
