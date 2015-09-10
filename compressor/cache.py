import json
import hashlib
import os
import socket
import time

try:
    from django.core.cache import caches
    def get_cache(name):
        return caches[name]
except ImportError:
    from django.core.cache import get_cache

from django.core.files.base import ContentFile
from django.utils.encoding import force_text, smart_bytes
from django.utils.functional import SimpleLazyObject

try:
    from importlib import import_module
except:
    from django.utils.importlib import import_module

from compressor.conf import settings
from compressor.storage import default_storage
from compressor.utils import get_mod_func

_cachekey_func = None


def get_hexdigest(plaintext, length=None):
    digest = hashlib.md5(smart_bytes(plaintext)).hexdigest()
    if length:
        return digest[:length]
    return digest


def simple_cachekey(key):
    return 'django_compressor.%s' % force_text(key)


def socket_cachekey(key):
    return 'django_compressor.%s.%s' % (socket.gethostname(), force_text(key))


def get_cachekey(*args, **kwargs):
    global _cachekey_func
    if _cachekey_func is None:
        try:
            mod_name, func_name = get_mod_func(
                settings.COMPRESS_CACHE_KEY_FUNCTION)
            _cachekey_func = getattr(import_module(mod_name), func_name)
        except (AttributeError, ImportError, TypeError) as e:
            raise ImportError("Couldn't import cache key function %s: %s" %
                              (settings.COMPRESS_CACHE_KEY_FUNCTION, e))
    return _cachekey_func(*args, **kwargs)


def get_mtime_cachekey(filename):
    return get_cachekey("mtime.%s" % get_hexdigest(filename))


def get_offline_hexdigest(render_template_string):
    return get_hexdigest(render_template_string)


def get_offline_cachekey(source):
    return get_cachekey("offline.%s" % get_offline_hexdigest(source))


def get_offline_manifest_filename():
    output_dir = settings.COMPRESS_OUTPUT_DIR.strip('/')
    return os.path.join(output_dir, settings.COMPRESS_OFFLINE_MANIFEST)


_offline_manifest = None


def get_offline_manifest():
    global _offline_manifest
    if _offline_manifest is None:
        filename = get_offline_manifest_filename()
        if default_storage.exists(filename):
            with default_storage.open(filename) as fp:
                _offline_manifest = json.loads(fp.read().decode('utf8'))
        else:
            _offline_manifest = {}
    return _offline_manifest


def flush_offline_manifest():
    global _offline_manifest
    _offline_manifest = None


def write_offline_manifest(manifest):
    filename = get_offline_manifest_filename()
    content = json.dumps(manifest, indent=2).encode('utf8')
    default_storage.save(filename, ContentFile(content))
    flush_offline_manifest()


def get_templatetag_cachekey(compressor, mode, kind):
    return get_cachekey(
        "templatetag.%s.%s.%s" % (compressor.cachekey, mode, kind))


def get_mtime(filename):
    if settings.COMPRESS_MTIME_DELAY:
        key = get_mtime_cachekey(filename)
        mtime = cache.get(key)
        if mtime is None:
            mtime = os.path.getmtime(filename)
            cache.set(key, mtime, settings.COMPRESS_MTIME_DELAY)
        return mtime
    return os.path.getmtime(filename)


def get_hashed_mtime(filename, length=12):
    try:
        filename = os.path.realpath(filename)
        mtime = str(int(get_mtime(filename)))
    except OSError:
        return None
    return get_hexdigest(mtime, length)


def get_hashed_content(filename, length=12):
    try:
        filename = os.path.realpath(filename)
    except OSError:
        return None

    # should we make sure that file is utf-8 encoded?
    with open(filename, 'rb') as file:
        return get_hexdigest(file.read(), length)


def get_precompiler_cachekey(command, contents):
    return hashlib.sha1(smart_bytes('precompiler.%s.%s' % (command, contents))).hexdigest()


def cache_get(key):
    packed_val = cache.get(key)
    if packed_val is None:
        return None
    val, refresh_time, refreshed = packed_val
    if (time.time() > refresh_time) and not refreshed:
        # Store the stale value while the cache
        # revalidates for another MINT_DELAY seconds.
        cache_set(key, val, refreshed=True,
            timeout=settings.COMPRESS_MINT_DELAY)
        return None
    return val


def cache_set(key, val, refreshed=False, timeout=None):
    if timeout is None:
        timeout = settings.COMPRESS_REBUILD_TIMEOUT
    refresh_time = timeout + time.time()
    real_timeout = timeout + settings.COMPRESS_MINT_DELAY
    packed_val = (val, refresh_time, refreshed)
    return cache.set(key, packed_val, real_timeout)


cache = SimpleLazyObject(lambda: get_cache(settings.COMPRESS_CACHE_BACKEND))
