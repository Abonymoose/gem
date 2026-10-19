# PyInstaller's bundled hook looks for the "webrtcvad" distribution, but the
# Windows wheels are published as "webrtcvad-wheels".
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("webrtcvad-wheels")
