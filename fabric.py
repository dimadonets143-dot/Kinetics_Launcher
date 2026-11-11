import os
import re

from . import mojang, net

META = "https://meta.fabricmc.net/v2"


def loader_versions(mc):
    data = net.get_json(f"{META}/versions/loader/{mc}", 20)
    return [d["loader"]["version"] for d in data]


def _stable(mc):
    data = net.get_json(f"{META}/versions/loader/{mc}", 20)
    if not data:
        raise RuntimeError(f"Fabric не поддерживает версию {mc}")
    for d in data:
        if d["loader"].get("stable"):
            return d["loader"]["version"]
    return data[0]["loader"]["version"]


def _installed_for(mc):
    have = [v for v in mojang.installed_versions() if v.startswith("fabric-loader-") and v.endswith("-" + mc)]

    def key(v):
        ver = v[len("fabric-loader-"):-(len(mc) + 1)]
        return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", ver))
    return max(have, key=key) if have else None


def install(mc, loader=None):
    """Скачивает профиль Fabric, возвращает id версии. Без лишних запросов в сеть."""
    if not loader or loader == "auto":
        have = _installed_for(mc)
        if have:
            return have
        loader = _stable(mc)
    vid = f"fabric-loader-{loader}-{mc}"
    p = mojang.version_json_path(vid)
    if not os.path.isfile(p):
        net.download(f"{META}/versions/loader/{mc}/{loader}/profile/json", p)
    return vid
