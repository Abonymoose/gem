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
    name = re.sub(r"\((?:R|TM|C)\)", "", name, flags=re.I)                 # "Realtek(R) Audio" -> "Realtek Audio"
    return re.sub(r"\s*\((?:\d+-\s*)?(.+?)\)\s*$", r" (\1)", name).strip()


def _words(text):
    return re.findall(r"[a-z0-9]+", re.sub(r"\((?:r|tm|c)\)", "", text.lower()))


ALIASES = {"headphones": ["headphone", "headset", "earphone", "airpods", "buds", "arctis", "hyperx", "wh-", "wf-"],
           "speakers": ["speaker", "realtek", "monitor", "display", "hdmi", "tv"]}
ORDINALS = {"first": 1, "one": 1, "1st": 1, "second": 2, "two": 2, "2nd": 2, "third": 3, "three": 3, "3rd": 3,
            "fourth": 4, "four": 4, "4th": 4, "fifth": 5, "five": 5, "5th": 5, "sixth": 6, "six": 6, "6th": 6,
            "last": -1}


def _listed():
    """The devices in the order Gem reads them out (virtual Steam outputs left out), and the current one's id."""
    devices, default = outputs()
    return [(i, n) for i, n in devices if "steam streaming" not in n.lower()], default


def _numbered(devices, default):
    return "; ".join("%d, %s%s" % (k, _short(n), " (playing now)" if i == default else "")
                     for k, (i, n) in enumerate(devices, 1))


def _pick(want, devices, default):
    """The device a request means: "the third one", "speakers", "realtek r audio", "benq"."""
    words = [w for w in _words(want) if w not in ("the", "my", "to", "one", "option", "device", "output", "audio",
                                                  "number", "r")] or _words(want)
    num = next((ORDINALS[w] for w in _words(want) if w in ORDINALS), None)
    if num is None:
        num = next((int(w) for w in _words(want) if w.isdigit() and 0 < int(w) <= len(devices)), None)
    if num is not None and (len(words) <= 1 or not any(w in " ".join(_words(n)) for _, n in devices for w in words)):
        return [devices[num - 1 if num > 0 else -1]] if devices and abs(num) <= len(devices) else []
    hints = ALIASES.get(want.rstrip("s") + "s", []) + ALIASES.get(want, [])
    match = [(i, n) for i, n in devices if any(h in n.lower() for h in hints)]
    if match:
        return match
    # Most words in common wins: "speakers realtek r audio" -> "Speakers (Realtek(R) Audio)"
    scored = [(sum(1 for w in words if w in _words(n)), (i, n)) for i, n in devices]
    best = max((s for s, _ in scored), default=0)
    return [d for s, d in scored if s == best] if best else []


@action("audio_output", "Switch which device plays sound (headphones, speakers, a device by name or by its number "
        "in the list, e.g. 'the second one'), or say which ones there are when no device is given.", "device?: str")
def audio_output(device=""):
    devices, default = _listed()
    want = (device or "").lower().strip()
    if not want:
        return "You have %s. Say switch to, and a number or a name." % _numbered(devices, default)
    match = _pick(want, devices, default)
    if not match:
        raise ActionError("I couldn't find %s. You have %s." % (device, _numbered(devices, default)))
    dev_id, name = next(((i, n) for i, n in match if i != default), match[0])
    if dev_id == default:
        return "You're already on %s." % _short(name)
    pol = _policy_config()
    for role in (0, 1, 2):                                       # console, multimedia, communications
        pol.SetDefaultEndpoint(dev_id, role)
    log.info("Audio output -> %s", name)
    return "Switched to %s." % _short(name)
