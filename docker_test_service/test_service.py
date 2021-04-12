from __future__ import print_function
import __builtin__
import os
import time

import pytest
import mock
import psutil
from tornado.tcpclient import TCPClient
from tornado.ioloop import IOLoop
from tornado import gen

import service

def test_service():
    process = psutil.Process(os.getpid())
    s = service.Service()
    last_rss = process.memory_info().rss
    s.init_pool(100)
    curr_rss = process.memory_info().rss
    assert curr_rss > service.TOTAL_SIZE
    s.dirty_memory() # Makesure this function is callable
    assert True

@pytest.fixture
def simple_tcp():
    s = service.Service()
    loop = IOLoop.current()
    server = service.SimpleTestServer(s, loop)
    server.listen(10505, '0.0.0.0')
    print('Start server')

TEST_TIME = 10000.0
TEST_DELTA = 0.01

@gen.coroutine
def client_run():
    process = psutil.Process(os.getpid())
    last_rss = process.memory_info().rss
    client = TCPClient()
    stream = yield client.connect('127.0.0.1', 10505)
    yield stream.write("100\n")
    data = yield stream.read_until(b"\n")
    assert data == "OK\n" # Should return OK
    curr_rss = process.memory_info().rss
    assert curr_rss > service.TOTAL_SIZE
    IOLoop.current().stop()

@pytest.mark.timeout(10)
def test_simple_test_server(simple_tcp):
    client_run()
    IOLoop.current().start()
    assert True

@mock.patch("time.time")
@mock.patch("__builtin__.print")
def test_periodic_callback(mock_print, mock_time):
    """periodic_callback should print out 'Missing <number>' when the function
    miss some periods
    """
    service.loop = mock.Mock()
    service.last = 100
    mock_time.return_value = service.last + service.TIMER_PERIOD
    service.periodic_callback()
    assert not mock_print.called
    mock_time.return_value = service.last + 2*service.MISSING_PERIOD
    service.periodic_callback()
    assert mock_print.called
