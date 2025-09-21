import bpy
from bpy.props import StringProperty, BoolProperty
from ..base import LuxCoreNodeTexture
from ... import icons
from ...utils import node as utils_node


def convert(string):
    separated = string.strip().split(",")
    return [float(elem) for elem in separated]


class LuxCoreNodeTexIrregularData(LuxCoreNodeTexture, bpy.types.Node):
    bl_label = "Irregular Data"

    equal_length: BoolProperty(update=utils_node.force_viewport_update, default=True)
    error: StringProperty(update=utils_node.force_viewport_update, )

    def update_data(self, context):
        try:
            wavelengths_converted = convert(self.wavelengths)
            data_converted = convert(self.data)
            self.equal_length = len(wavelengths_converted) == len(data_converted)
            self.error = ""
        except ValueError as error:
            print(error)
            self.error = str(error)
        utils_node.force_viewport_update(self, context)

    wavelengths: StringProperty(name="", default="580.0, 620.0, 660.0", update=update_data,
                                 description="Comma-separated list of values")
    data: StringProperty(name="", default="0.0, 0.000015, 0.0", update=update_data,
                          description="Comma-separated list of values")

    def init(self, context):
        self.outputs.new("LuxCoreSocketColor", "Color")

    def draw_buttons(self, context, layout):
        layout.label(text="Wavelengths:")
        layout.prop(self, "wavelengths")
        layout.label(text="Data:")
        layout.prop(self, "data")

        if not self.equal_length:
            layout.label(text="Both lists need the same number of values!", icon=icons.ERROR)

        if self.error:
            layout.label(text=self.error, icon=icons.ERROR)

    def sub_export(self, exporter, depsgraph, props, luxcore_name=None, output_socket=None):
        definitions = {
            "type": "irregulardata",
            "wavelengths": convert(self.wavelengths),
            "data": convert(self.data),
        }
        return self.create_props(props, definitions, luxcore_name)
