import time
import copy
from cStringIO import StringIO

class InMemoryCache(object):
    def __init__(self):
        self.cache = {}

    def set(self, key, status, response_headers, response_body, ttl=-1):
        expire_timestamp = int(time.time()) + ttl if ttl > 0 else -1
        self.cache[key] = {
            'status': status,
            'response_headers': copy.deepcopy(response_headers),
            'response_body': copy.deepcopy(response_body),
            'expire_timestamp': expire_timestamp
        }

    def get(self, key):
        r = self.cache.get(key, {'expire_timestamp': 0})
        if self._is_expired(r):
            return None, None, None
        else:
            return r['status'], copy.deepcopy(r['response_headers']), copy.deepcopy(r['response_body'])

    def _is_expired(self, response_metadata):
        ts = response_metadata['expire_timestamp']
        return ts != -1 and int(time.time()) > ts


class WSGICache(object):
    def __init__(self, app, ignore_headers=['Set-Cookie']):
        self.app = app
        self.cache = InMemoryCache()
        self.ignore_headers = set(ignore_headers)

    def __call__(self, environ, start_response):
        cache_key = environ['PATH_INFO'] + environ['QUERY_STRING']
        status, response_headers, response = self.cache.get(cache_key)

        if response is None:
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
                    self.cache.set(cache_key, sr.status, sr.response_headers, response, cache_for_ttl)

            write = start_response(sr.status, sr.response_headers, sr.exc_info)
            if sio.tell(): # position is not 0
                sio.seek(0)
                write(sio.read())
        else:
            start_response(status, response_headers, None)

        for data in response:
            yield data