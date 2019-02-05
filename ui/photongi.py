from bl_ui.properties_render import RenderButtonsPanel
from bpy.types import Panel
from . import icons


class LUXCORE_RENDER_PT_photongi(RenderButtonsPanel, Panel):
    COMPAT_ENGINES = {"LUXCORE"}
    bl_label = "LuxCore PhotonGI Cache"

    @classmethod
    def poll(cls, context):
        # PhotonGI is currently not supported by Bidir, so we hide the settings in this case
        return context.scene.render.engine == "LUXCORE" and context.scene.luxcore.config.engine != "BIDIR"

    def draw_header(self, context):
        self.layout.prop(context.scene.luxcore.config.photongi, "enabled", text="")

    def draw(self, context):
        layout = self.layout
        photongi = context.scene.luxcore.config.photongi
        layout.active = photongi.enabled

        if not photongi.indirect_enabled and not photongi.caustic_enabled:
            layout.label(text="All caches disabled", icon=icons.WARNING)

        row = layout.row(align=True)
        row.prop(photongi, "photon_maxcount")
        row.prop(photongi, "photon_maxdepth")

        col = layout.column()
        col.prop(photongi, "indirect_enabled")
        row = col.row(align=True)
        row.active = photongi.indirect_enabled
        row.prop(photongi, "indirect_maxsize")
        row.prop(photongi, "indirect_lookup_radius")

        col = layout.column()
        col.prop(photongi, "caustic_enabled")
        row = col.row(align=True)
        row.active = photongi.caustic_enabled
        row.prop(photongi, "caustic_maxsize")
        row.prop(photongi, "caustic_lookup_radius")

        layout.prop(photongi, "debug")
        if (photongi.debug == "showindirect" and not photongi.indirect_enabled) or (
                photongi.debug == "showcaustic" and not photongi.caustic_enabled):
            layout.label(text="Can't show this cache (disabled)", icon=icons.WARNING)