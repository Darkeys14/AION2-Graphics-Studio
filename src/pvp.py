from core import PRESETS


def quality_profile():
    values = PRESETS['PvP'].copy()
    values.update({'sg.ViewDistanceQuality': 1, 'sg.PostProcessQuality': 0,
                   'sg.ShadingQuality': 0, 'sg.MassiveGameQuality': 0, 'sg.ModelQuality': 1})
    return values


def tested_city_profile():
    """The exact three Engine.ini values used in the repeated city measurements."""
    return {'r.ShadowQuality': '0', 'r.ViewDistanceScale': '0.7',
            'r.SkeletalMeshLODBias': '1'}


def renderer_profile(disable_lumen=True, unlimited=True):
    values = {'r.ShadowQuality': '0', 'r.SSR.Quality': '0', 'r.MotionBlurQuality': '0',
              'r.DepthOfFieldQuality': '0', 'r.LensFlareQuality': '0', 'r.AmbientOcclusionLevels': '0',
              'r.MaxAnisotropy': '4', 'r.Streaming.LimitPoolSizeToVRAM': '1'}
    if disable_lumen:
        values.update({'r.Lumen.DiffuseIndirect.Allow': '0', 'r.Lumen.Reflections.Allow': '0'})
    if unlimited:
        values['t.MaxFPS'] = '0'
    return values
