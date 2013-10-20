import unittest
import time
import accelerator
from werkzeug.test import Client as TestClient
from werkzeug.wrappers import BaseResponse
from flask import Flask, request, make_response

orig_time = time.time
def mock_time(new_time):
    def mock():
        time.time = orig_time # Trigger once only
        return float(new_time)
    time.time = mock

class TestClientResponse(BaseResponse):
    def id(self):
        return int(self.data)

app_code_triggered = False
response_id = -1 # Used to verify if response is cached or not
cache_time = 5

app = Flask(__name__)
app.debug = True
app.secret_key = "avocado"

@app.route("/heavy")
def perform_expensive_calculation():
    time.sleep(2) # Emulate CPU time
    return "Heavy lifting done!"

@app.route("/uncached")
def uncached():
    return str(response_id)

@app.route("/cached", methods=["GET", "POST"])
def cached():
    status_code = request.args.get('status_code', 200)
    set_cookie = request.args.get('set_cookie', 'false')
    tags = request.args.getlist('tags')
    request.environ['accelerator.cache_for'] = cache_time
    request.environ['accelerator.tags'] = tags

    resp = make_response(str(response_id), status_code)
    if set_cookie == 'true':
        resp.set_cookie('response_id', str(response_id))
    
    return resp

class BaseTestCase(unittest.TestCase):
    cache_store = None # Defaults to InMemoryCache

    def setUp(self):
        self._reset()
        self.app = accelerator.WSGIAccelerator(app, cache_store=self.cache_store)
        self.client = TestClient(self.app, response_wrapper=TestClientResponse)

    def tearDown(self):
        pass

    def _reset(self):
        global response_id, cache_time
        response_id = 1
        cache_time = 5

    def _increment_id(self):
        global response_id
        old_id = response_id
        response_id += 1
        return old_id

    def test_uncached_response(self):
        r = self.client.get('/uncached')
        self.assertEquals(response_id, r.id())

    def test_cached_response(self):
        self.assertEquals(response_id, self.client.get('/cached').id())
        old_id = self._increment_id()
        self.assertEquals(old_id, self.client.get('/cached').id())
        mock_time(time.time() + 10)
        self.assertEquals(response_id, self.client.get('/cached').id())

    def test_only_get_method(self):
        self.assertEquals(response_id, self.client.post('/cached').id())
        self._increment_id()
        self.assertEquals(response_id, self.client.post('/cached').id())
        self._increment_id()
        self.assertEquals(response_id, self.client.get('/cached').id())

    def test_only_2xx_responses(self):
        self.assertEquals(response_id, self.client.get('/cached?status_code=401').id())
        self._increment_id()
        self.assertEquals(response_id, self.client.get('/cached?status_code=401').id())

    def test_custom_status_code(self):
        self.assertEquals(response_id, self.client.get('/cached?status_code=250').id())
        old_id = self._increment_id()
        self.assertEquals(old_id, self.client.get('/cached?status_code=250').id())

    def test_strip_headers(self):
        r = self.client.get('/cached?set_cookie=true')
        self.assertEquals(response_id, r.id())
        self.assertIn('Set-Cookie', r.headers)

        self._increment_id()

        r = self.client.get('/cached?set_cookie=true')
        self.assertEquals(response_id, r.id())
        self.assertIn('Set-Cookie', r.headers)

    def test_etag(self):
        r = self.client.get('/cached')
        self.assertEquals(response_id, r.id())
        self.assertEqual(self.app.cache.etag_hash(r.data), r.headers['ETag'])

        old_id = self._increment_id()

        r = self.client.get('/cached', headers=[('ETag', self.app.cache.etag_hash(r.data))])
        self.assertEquals(r.status_code, 304)
        self.assertEquals(r.data, '')

        # Should be cached even without ETag
        r = self.client.get('/cached')
        self.assertEquals(r.status_code, 200)
        self.assertEquals(old_id, r.id())

    def test_tags(self):
        tag_url = '/cached?tags=foo'
        self.assertEquals(response_id, self.client.get(tag_url).id())
        old_id = self._increment_id()
        self.assertEquals(old_id, self.client.get(tag_url).id())
        self.app.invalidate_tag(['foo', 'bogus'])
        self.assertEquals(response_id, self.client.get(tag_url).id())

    def test_multiple_tags(self):
        global cache_time
        tag_url1 = '/cached?tags=foo&tags=bar'
        tag_url2 = '/cached?tags=baz&tags=bar'
        tag_url3 = '/cached?tags=baz&tags=qux'

        self.assertEquals(response_id, self.client.get(tag_url1).id())
        self.assertEquals(response_id, self.client.get(tag_url2).id())
        self.assertEquals(response_id, self.client.get(tag_url3).id())

        old_id = self._increment_id()

        self.assertEquals(old_id, self.client.get(tag_url1).id())
        self.assertEquals(old_id, self.client.get(tag_url2).id())
        self.assertEquals(old_id, self.client.get(tag_url3).id())

        self.app.invalidate_tag(['bar', 'bogus'])
        cache_time = -1 # Disable creation of new cache entries
        self.assertEquals(response_id, self.client.get(tag_url1).id())
        self.assertEquals(response_id, self.client.get(tag_url2).id())
        self.assertEquals(old_id, self.client.get(tag_url3).id())

        self.app.invalidate_tag(['qux'])
        self.assertEquals(response_id, self.client.get(tag_url1).id())
        self.assertEquals(response_id, self.client.get(tag_url2).id())
        self.assertEquals(response_id, self.client.get(tag_url3).id())

        self.assertEquals(len(self.app.cache.get_path_keys_by_tag('foo')), 0)
        self.assertEquals(len(self.app.cache.get_path_keys_by_tag('bar')), 0)
        self.assertEquals(len(self.app.cache.get_path_keys_by_tag('baz')), 0)
        self.assertEquals(len(self.app.cache.get_path_keys_by_tag('qux')), 0)

try:
    import redis
    try:
        r = redis.Redis()
        r.info()

        class RedisTestCase(BaseTestCase):
            def setUp(self):
                r = redis.Redis()
                r.flushdb()
                self.cache_store = accelerator.stores.RedisCache(r)
                super(RedisTestCase, self).setUp()
    except redis.exceptions.ConnectionError as e:
        print "Unable to connect to local Redis server, skipping Redis tests"
except ImportError as ie:
    print "No Redis library found, skipping Redis tests"


if __name__ == '__main__':
    unittest.main()