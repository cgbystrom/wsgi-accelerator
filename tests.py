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
    request.environ['accelerator.cache_for'] = 5
    status_code = request.args.get('status_code', 200)
    set_cookie = request.args.get('set_cookie', 'false')

    resp = make_response(str(response_id), status_code)
    if set_cookie == 'true':
        resp.set_cookie('response_id', str(response_id))
    
    return resp

class AcceleratorTestCase(unittest.TestCase):

    def setUp(self):
        self._reset_id()
        self.app = accelerator.WSGICache(app)
        self.client = TestClient(self.app, response_wrapper=TestClientResponse)

    def tearDown(self):
        pass

    def _reset_id(self):
        global response_id
        response_id = 1

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

    def test_strip_headers(self):
        r = self.client.get('/cached?set_cookie=true')
        self.assertEquals(response_id, r.id())
        self.assertIn('Set-Cookie', r.headers)

        self._increment_id()

        r = self.client.get('/cached?set_cookie=true')
        self.assertEquals(response_id, r.id())
        self.assertIn('Set-Cookie', r.headers)


if __name__ == '__main__':
    unittest.main()