"""Switch where sound comes out: "switch to my headphones", "use the speakers", "what am I playing sound through?"."""
import logging
import re

from ..actions import ActionError, action

log = logging.getLogger("gem.audio_devices")

_policy = None


def _policy_config():
    """IPolicyConfig: the (undocumented, long-stable) Windows interface the Sound settings use to set defaults."""
    global _policy
    if _policy is not None:
        return _policy
    import comtypes
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
    from ctypes import POINTER, c_int, c_void_p
    from ctypes.wintypes import LPCWSTR

    class IPolicyConfig(IUnknown):
        _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetMixFormat", (["in"], LPCWSTR), (["out"], POINTER(c_void_p))),
            COMMETHOD([], HRESULT, "GetDeviceFormat", (["in"], LPCWSTR), (["in"], c_int), (["out"], POINTER(c_void_p))),
            COMMETHOD([], HRESULT, "ResetDeviceFormat", (["in"], LPCWSTR)),
            COMMETHOD([], HRESULT, "SetDeviceFormat", (["in"], LPCWSTR), (["in"], c_void_p), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "GetProcessingPeriod", (["in"], LPCWSTR), (["in"], c_int),
                      (["out"], POINTER(c_void_p)), (["out"], POINTER(c_void_p))),
            COMMETHOD([], HRESULT, "SetProcessingPeriod", (["in"], LPCWSTR), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "GetShareMode", (["in"], LPCWSTR), (["out"], POINTER(c_void_p))),
            COMMETHOD([], HRESULT, "SetShareMode", (["in"], LPCWSTR), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "GetPropertyValue", (["in"], LPCWSTR), (["in"], c_void_p), (["out"], POINTER(c_void_p))),
            COMMETHOD([], HRESULT, "SetPropertyValue", (["in"], LPCWSTR), (["in"], c_void_p), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "SetDefaultEndpoint", (["in"], LPCWSTR), (["in"], c_int)),
            COMMETHOD([], HRESULT, "SetEndpointVisibility", (["in"], LPCWSTR), (["in"], c_int)),
        ]

    clsid = GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")
    _policy = comtypes.CoCreateInstance(clsid, IPolicyConfig, comtypes.CLSCTX_ALL)
    return _policy


def outputs():
    """[(id, friendly name)] of active playback devices, and the current default's id."""
    from pycaw.pycaw import AudioUtilities
    from pycaw.constants import DEVICE_STATE, EDataFlow
    enum = AudioUtilities.GetDeviceEnumerator()
    coll = enum.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
    found = []
    for i in range(coll.GetCount()):
        dev = coll.Item(i)
        found.append((dev.GetId(), AudioUtilities.CreateDevice(dev).FriendlyName))
    default = enum.GetDefaultAudioEndpoint(EDataFlow.eRender.value, 1).GetId()       # eMultimedia
    return found, default


def _short(name):
    return re.sub(r"\s*\((?:\d+-\s*)?(.+?)\)\s*$", r" (\1)", name)


ALIASES = {"headphones": ["headphone", "headset", "earphone", "airpods", "buds", "arctis", "hyperx", "wh-", "wf-"],
           "speakers": ["speaker", "realtek", "monitor", "display", "hdmi", "tv"]}


@action("audio_output", "Switch which device plays sound (headphones, speakers, a device by name), or say which one "
        "is in use when no device is given.", "device?: str")
def audio_output(device=""):
    devices, default = outputs()
    current = next((n for i, n in devices if i == default), "unknown")
    want = (device or "").lower().strip()
    if not want:
        others = [_short(n) for i, n in devices if i != default and "steam streaming" not in n.lower()]
        return "Sound is playing through %s.%s" % (_short(current), (" You can also switch to %s." % ", ".join(others))
                                                    if others else "")
    hints = ALIASES.get(want.rstrip("s") + "s", []) + ALIASES.get(want, []) + [want]
    match = [(i, n) for i, n in devices if any(h in n.lower() for h in hints)]
    if not match:
        names = ", ".join(_short(n) for _, n in devices)
        raise ActionError("I couldn't find %s. You have %s." % (device, names))
    dev_id, name = next(((i, n) for i, n in match if i != default), match[0])
    if dev_id == default:
        return "You're already on %s." % _short(name)
    pol = _policy_config()
    for role in (0, 1, 2):                                       # console, multimedia, communications
        pol.SetDefaultEndpoint(dev_id, role)
    log.info("Audio output -> %s", name)
    return "Switched to %s." % _short(name)
