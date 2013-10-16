"""
Redis-based cache store for WSGI accelerator
http://redis.io/
"""

import hashlib
import time


class RedisCache(object):
    def __init__(self, redis_client, key_prefix='acc.', json=None):
        self.redis_client = redis_client
        self.key_prefix = key_prefix
        if not json:
            import json as builtin_json
            self.json = builtin_json

    def set(self, key, status, response_headers, response_body, ttl=-1, tags=[]):
        expire_timestamp = int(time.time()) + ttl if ttl > 0 else -1
        body = ''.join(response_body)
        etag = self.etag_hash(body)

        cache_entry = {
            'status': status,
            # FIXME: Use separate keys rather than using inline JSON serialization?
            'response_headers': self.json.dumps(response_headers),
            'response_body': body,
            'expire_timestamp': expire_timestamp,
            'etag': etag,
            'tags': self.json.dumps(tags)
        }

        self.redis_client.hmset(self._key(key), cache_entry)
        self.add_tag(key, tags)
        return etag

    def get(self, key):
        entry = self.redis_client.hgetall(self._key(key))
        if not entry:
            return None

        entry['response_headers'] = self.json.loads(entry['response_headers'])
        entry['expire_timestamp'] = int(entry['expire_timestamp'])
        entry['tags'] = self.json.loads(entry['tags'])

        if self._is_expired(entry):
            self.redis_client.delete(self._key(key))
            self.remove_tag(key, entry['tags'])
            return None

        return entry

    def add_tag(self, path_key, tags):
        for tag in tags:
            self.redis_client.sadd(self._tag_key(tag), path_key)

    def remove_tag(self, path_key, tags):
        for tag in tags:
            self.redis_client.srem(self._tag_key(tag), path_key)

    def get_path_keys_by_tag(self, tag):
        return self.redis_client.smembers(self._tag_key(tag))

    def invalidate_tag(self, tags):
        keys_with_dirty_tags = {}
        for tag in tags:
            for path_key in self.redis_client.smembers(self._tag_key(tag)):
                dirty_tags = self.invalidate_key(path_key)
                keys_with_dirty_tags.setdefault(path_key, set()).update(dirty_tags)

        for key, tags in keys_with_dirty_tags.iteritems():
            self.remove_tag(key, tags)

    def invalidate_key(self, path_key):
        entry = self.get(path_key)
        dirty_tags =[]
        if entry:
            dirty_tags = entry['tags']
            self.redis_client.delete(self._key(path_key))

        return dirty_tags

    def etag_hash(self, value):
        return hashlib.md5(value).hexdigest()

    def _is_expired(self, entry):
        ts = entry['expire_timestamp']
        return ts != -1 and int(time.time()) > ts

    def _key(self, key):
        return self.key_prefix + key

    def _tag_key(self, tag):
        return "%stag.%s" % (self.key_prefix, tag)