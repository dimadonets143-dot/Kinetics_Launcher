import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = "KineticsLauncher/1.0 (+python-urllib)"


def _open(url, timeout=30):
    import urllib.request  # ленивый импорт: ускоряет старт окна
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url, timeout=30):
    with _open(url, timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_ok(path, sha1=None, size=None, strict=False):
    if not os.path.isfile(path):
        return False
    if size is not None and os.path.getsize(path) != size:
        return False
    if strict and sha1:
        return sha1_file(path) == sha1
    return True


def download(url, dest, sha1=None, retries=3, on_bytes=None):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last = None
    for attempt in range(retries):
        tmp = dest + ".part"
        try:
            with _open(url, 60) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if on_bytes:
                        on_bytes(done, total)
            if sha1 and sha1_file(tmp) != sha1:
                raise IOError("контрольная сумма не совпала")
            os.replace(tmp, dest)
            return
        except Exception as e:  # noqa
            last = e
            time.sleep(1 + attempt)
    raise RuntimeError(f"Не удалось скачать {url}: {last}")


def download_many(tasks, threads=8, progress=None, strict=False):
    """tasks: список dict(url, path, sha1?, size?). Возвращает число скачанных файлов."""
    todo = [t for t in tasks if not file_ok(t["path"], t.get("sha1"), t.get("size"), strict)]
    total = len(todo)
    if progress:
        progress(0, total)
    if not todo:
        return 0
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, int(threads))) as ex:
        futs = [ex.submit(download, t["url"], t["path"], t.get("sha1")) for t in todo]
        for f in as_completed(futs):
            f.result()
            done += 1
            if progress:
                progress(done, total)
    return total
