import hashlib
import time
import copy
from cStringIO import StringIO

class InMemoryCache(object):
    def __init__(self):
        self.cache = {}
        self.tags_lookup = {}

    def set(self, key, status, response_headers, response_body, ttl=-1, tags=[]):
        expire_timestamp = int(time.time()) + ttl if ttl > 0 else -1
        body = copy.deepcopy(response_body)
        etag = self.etag_hash(''.join(body))
        self.cache[key] = {
            'status': status,
            'response_headers': copy.deepcopy(response_headers),
            'response_body': body,
            'expire_timestamp': expire_timestamp,
            'etag': etag,
            'tags': tags
        }
        self.add_tag(key, tags)
        return etag

    def get(self, key):
        r = self.cache.get(key, {'expire_timestamp': 0})
        if self._is_expired(r):
            return None
        else:
            return copy.deepcopy(r)

    def add_tag(self, key, tags):
        for t in tags:
            self.tags_lookup.setdefault(t, set()).add(key)

    def remove_tag(self, key, tags):
        for t in tags:
            if t not in self.tags_lookup:
                continue

            self.tags_lookup[t].discard(key)
            if len(self.tags_lookup[t]) == 0:
                del self.tags_lookup[t]

    def invalidate_tag(self, tags):
        keys_with_dirty_tags = {}
        tags_lookup = self.tags_lookup.copy()
        for t in tags:
            for key in tags_lookup.get(t, set()):
                dirty_tags = self.invalidate_key(key)
                keys_with_dirty_tags.setdefault(key, set()).update(set(dirty_tags))

        for key, tags in keys_with_dirty_tags.iteritems():
            self.remove_tag(key, tags)

    def invalidate_key(self, key):
        dirty_tags = []
        if key in self.cache:
            dirty_tags = self.cache[key].get('tags', [])
            del self.cache[key]
        return dirty_tags

    def etag_hash(self, value):
        return hashlib.md5(value).hexdigest()

    def _is_expired(self, response_metadata):
        ts = response_metadata['expire_timestamp']
        return ts != -1 and int(time.time()) > ts


class WSGICache(object):
    def __init__(self, app, ignore_headers=['Set-Cookie']):
        self.app = app
        self.cache = InMemoryCache()
        self.ignore_headers = set(ignore_headers)

    def invalidate_tag(self, tags):
        self.cache.invalidate_tag(tags)

    def __call__(self, environ, start_response):
        cache_key = environ['PATH_INFO'] + environ['QUERY_STRING']
        cache_metadata = self.cache.get(cache_key)

        if cache_metadata is None:
            # Cache empty, proceed as normal
            sio = StringIO()

            def _start_response(status, response_headers, exc_info=None):
                _start_response.status = status
                _start_response.response_headers = response_headers
                _start_response.exc_info = exc_info
                return sio.write
            sr = _start_response

            # FIXME: Is this correct WSGI behavior with list() ?
            response = list(self.app(environ, _start_response))

            cache_for_ttl = environ.get('accelerator.cache_for', -1)
            if cache_for_ttl > 0 and environ['REQUEST_METHOD'] == 'GET' and _start_response.status[0] == '2':
                headers_ok = all([h[0] not in self.ignore_headers for h in sr.response_headers])
                if headers_ok:
                    tags = environ.get('accelerator.tags', [])
                    etag = self.cache.set(cache_key, sr.status, sr.response_headers, response, cache_for_ttl, tags)
                    sr.response_headers.append(('ETag', etag))

            write = start_response(sr.status, sr.response_headers, sr.exc_info)
            if sio.tell(): # position is not 0
                sio.seek(0)
                write(sio.read())
        else:
            if environ.get('HTTP_ETAG', None) == cache_metadata['etag']:
                start_response('304 Not Modified', [], None)
                response = ['']
            else:
                response = cache_metadata['response_body']
                start_response(cache_metadata['status'], cache_metadata['response_headers'], None)

        for data in response:
            yield data