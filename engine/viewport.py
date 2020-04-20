from time import time
from ..bin import pyluxcore
from .. import export
from ..draw.viewport import FrameBuffer
from .. import utils
from ..utils import render as utils_render
from ..utils.errorlog import LuxCoreErrorLog
from ..export.config import convert_viewport_engine

# Executed in separate thread
# TODO handle the case that the user cancelled the viewport render (engine will be deleted)
#  maybe save a reference to this thread in engine and join it in engine.__del__()?
def start_session(engine):
    try:
        engine.session.Start()
        engine.viewport_start_time = time()
    except Exception as error:
        del engine.session
        engine.session = None
        # Reset the exporter to invalidate all caches
        engine.exporter = None

        engine.update_stats("Error: ", str(error))
        LuxCoreErrorLog.add_error(error)

        import traceback
        traceback.print_exc()

    # TODO use lock when changing starting_session? Not strictly necessary
    #  due to CPython implementation details, but might be cleaner
    engine.starting_session = False


def view_update(engine, context, depsgraph, changes=None):
    start = time()
    if engine.starting_session:
        # Prevent deadlock
        return

    LuxCoreErrorLog.clear(force_ui_update=False)

    if engine.session is None:
        if not engine.viewport_starting_message_shown:
            # Let one engine.view_draw() happen so it shows a message in the UI
            return
        
        try:
            print("=" * 50)
            print("[Engine/Viewport] New session")
            engine.exporter = export.Exporter()
            engine.session = engine.exporter.create_session(depsgraph, context, engine=engine)
            # Start in separate thread to avoid blocking the UI
            engine.starting_session = True
            import _thread
            _thread.start_new_thread(start_session, (engine,))
        except Exception as error:
            del engine.session
            engine.session = None
            # Reset the exporter to invalidate all caches
            engine.exporter = None

            engine.update_stats("Error: ", str(error))
            LuxCoreErrorLog.add_error(error)

            import traceback
            traceback.print_exc()
        return

    s = time()
    changes = engine.exporter.get_changes(depsgraph, context, changes)
    print("view_update(): checking for changes took %.1f ms" % ((time() - s) * 1000))

    if changes:
        s = time()
        # We have to re-assign the session because it might have been replaced due to filmsize change
        engine.session = engine.exporter.update(depsgraph, context, engine.session, changes)
        engine.viewport_start_time = time()

        if engine.framebuffer:
            engine.framebuffer.reset_denoiser()
        print("view_update(): applying changes took %.1f ms" % ((time() - s) * 1000))
    print("view_update() took %.1f ms" % ((time() - start) * 1000))


def view_draw(engine, context, depsgraph):
    start = time()
    scene = depsgraph.scene_eval
    
    if engine.starting_session:
        engine.tag_redraw()
        return
    
    if engine.session is None:
        config = scene.luxcore.config
        definitions = {}
        luxcore_engine, _ = convert_viewport_engine(context, scene, definitions, config)
        message = ""
        
        if luxcore_engine.endswith("OCL"):
            # Create dummy renderconfig to check if we have to compile OpenCL kernels
            luxcore_scene = pyluxcore.Scene()
            definitions = {
                "scene.camera.type": "perspective",
            }
            luxcore_scene.Parse(utils.create_props("", definitions))
            
            definitions = {
                "renderengine.type": "RTPATHOCL",
                "sampler.type": "TILEPATHSAMPLER",
                "scene.epsilon.min": config.min_epsilon,
                "scene.epsilon.max": config.max_epsilon,
            }
            config_props = utils.create_props("", definitions)
            renderconfig = pyluxcore.RenderConfig(config_props, luxcore_scene)
            
            if not renderconfig.HasCachedKernels():
                message = "Compiling OpenCL kernels (just once, takes a few minutes)"
        
        engine.update_stats("Starting viewport render", message)
        engine.viewport_starting_message_shown = True
        engine.tag_update()
        engine.tag_redraw()
        return

    if not engine.framebuffer or engine.framebuffer.needs_replacement(context, scene):
        print("new framebuffer")
        engine.framebuffer = FrameBuffer(engine, context, scene)

    framebuffer = engine.framebuffer

    # Check for changes because some actions in Blender (e.g. moving the viewport
    # camera) do not trigger a view_update() call, but only a view_draw() call.
    s = time()
    changes = engine.exporter.get_viewport_changes(depsgraph, context)
    # print("view_draw(): checking for changes took %.1f ms" % ((time() - s) * 1000))

    if changes & export.Change.REQUIRES_VIEW_UPDATE:
        engine.tag_redraw()
        view_update(engine, context, depsgraph, changes)
        return
    elif changes & export.Change.CAMERA:
        # Only update in view_draw if it is a camera update,
        # for everything else we call view_update().
        # We have to re-assign the session because it might have been
        # replaced due to filmsize change.
        s = time()
        engine.session = engine.exporter.update(depsgraph, context, engine.session, export.Change.CAMERA)
        engine.viewport_start_time = time()
        # print("view_draw(): camera update took %.1f ms" % ((time() - s) * 1000))

    if utils.in_material_shading_mode(context):
        if not engine.session.IsInPause():
            engine.session.WaitNewFrame()
            engine.session.UpdateStats()
            framebuffer.update(engine.session, scene)
            engine.update_stats("", "")

            stats = engine.session.GetStats()
            samples = stats.Get("stats.renderengine.pass").GetInt()

            if samples >= 5:
                print("[Engine/Viewport] Pausing session")
                engine.session.Pause()
            else:
                engine.tag_redraw()
        framebuffer.draw(engine, context, scene)
        return

    # Check if we need to pause the viewport render
    # (note: the LuxCore stat "stats.renderengine.time" is not reliable here)
    rendered_time = time() - engine.viewport_start_time
    halt_time = scene.luxcore.viewport.halt_time
    status_message = ""

    if rendered_time > halt_time:
        if not engine.session.IsInPause():
            print("[Engine/Viewport] Pausing session")
            engine.session.Pause()
        status_message = "(Paused)"

        if framebuffer.denoiser_result_cached:
            status_message = "(Paused, Denoiser Done)"
        else:
            if framebuffer.is_denoiser_active():
                if framebuffer.is_denoiser_done():
                    status_message = "(Paused, Denoiser Done)"
                    framebuffer.load_denoiser_result(scene) # TODO warning, now scene instead of context!
                else:
                    status_message = "(Paused, Denoiser Working ...)"
                    engine.tag_redraw()
            elif context.scene.luxcore.viewport.denoise:
                try:
                    framebuffer.start_denoiser(engine.session)
                    engine.tag_redraw()
                except Exception as error:
                    status_message = "Could not start denoiser: %s" % error
    else:
        # Not in pause yet, keep drawing
        s = time()
        engine.session.WaitNewFrame()
        # print("view_draw(): session.WaitNewFrame() took %.1f ms" % ((time() - s) * 1000))
        try:
            s = time()
            engine.session.UpdateStats()
            # print("view_draw(): session.UpdateStats() took %.1f ms" % ((time() - s) * 1000))
        except RuntimeError as error:
            print("[Engine/Viewport] Error during UpdateStats():", error)
        s = time()
        framebuffer.update(engine.session, scene)
        framebuffer.reset_denoiser()
        engine.tag_redraw()
        # print("view_draw(): framebuffer update took %.1f ms" % ((time() - s) * 1000))

    s = time()
    framebuffer.draw(engine, context, scene)
    # print("view_draw(): framebuffer drawing took %.1f ms" % ((time() - s) * 1000))

    # Show formatted statistics in Blender UI
    s = time()
    config = engine.session.GetRenderConfig()
    stats = engine.session.GetStats()
    pretty_stats = utils_render.get_pretty_stats(config, stats, scene, context)
    engine.update_stats(pretty_stats, status_message)
    # print("view_draw(): showing stats in UI took %.1f ms" % ((time() - s) * 1000))

    # print("view_draw() took %.1f ms" % ((time() - start) * 1000))
