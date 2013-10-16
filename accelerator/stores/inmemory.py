import hashlib
import time
import copy


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