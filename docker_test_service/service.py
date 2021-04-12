#!/usr/bin/env python
"""This is a simple service to simulate RAM intensive service.

Mobile EU requests to the simple service deployed as a container on the edge
server with the required dirty memory rate dr . The simple service will
allocate amount of memory every second according to the requested dirty memory
rate to simulate an intensive RAM application. Additionally, the simple service
reads out clock and sleep every 100 milliseconds. We compare the difference
between two reading numbers to measure the downtime service from the container
point of view.

Service flow:
- The service initiates a memory pool which has size 1GB
- The client connects to the services and send a number e.g "100\n"
- The service accepts this number and send back an "OK\n" message.
- Every second, the service create 100MB dirty memory.
- Every 100ms, the service readout clock and compare with the last clock.

"""
from __future__ import print_function
from tornado.tcpserver import TCPServer
from tornado.iostream import StreamClosedError
from tornado.ioloop import IOLoop
from tornado import gen

import os
import functools
import time
import random
import logging

TIMER_PERIOD = 0.1
MISSING_PERIOD = 4*TIMER_PERIOD
TOTAL_SIZE = 2**30 # 1 GiB
MEM_UNIT = 2**20 # 1MiB

def dirty_memory_in_mb(mem, x):
    mem.remove(random.choice(mem))
    mem.append(bytearray(x*2**20))

class Service(object):
    """
    An memory intensity service
    """
    MEM = None
    SIZE = 0

    @staticmethod
    def init_pool(request_size):
        Service.MEM =[bytearray(request_size*MEM_UNIT)
                        for i in range(TOTAL_SIZE//(request_size*MEM_UNIT))]
        Service.SIZE = request_size

    @staticmethod
    def dirty_memory():
        if Service.SIZE != 0:
            dirty_memory_in_mb(Service.MEM, Service.SIZE)

class ClientHandler(object):
    def __init__(self, stream, service):
        self.stream = stream
        self.io_loop = stream.io_loop
        self.client_id = None
        self.service = service
        self.stream.read_until(b"\n", callback=self.on_receive)
        self.is_alloc_msg = True
        self.mem = []
        self.last = 0
        self.periodic_handler = None
        self.stream.set_close_callback(self.close)

    def on_receive(self, data):
        global mem
        if self.is_alloc_msg:
            self.requested_mem = int(data.rstrip("\n"))
            self.service.init_pool(self.requested_mem)
            self.stream.write("OK\n".encode())
            self.last = time.time()

    def close(self):
        print('Closed')
        if self.periodic_handler is not None:
            self.io_loop.remove_timeout(self.periodic_handler)
        self.mem = []

class SimpleTestServer(TCPServer):
    def __init__(self, service, loop):
        super(SimpleTestServer, self).__init__()
        self.service = service
        self.loop = loop
        self.loop.call_later(1, self.periodic_dirty)

    def handle_stream(self, stream, address):
        print('Receive from {}'.format(address))
        ClientHandler(stream, self.service)

    def periodic_dirty(self):
        self.service.dirty_memory()
        self.loop.call_later(1, self.periodic_dirty)

def periodic_callback():
    global last
    global loop
    curr = time.time()
    if (curr - last) > MISSING_PERIOD:
        print('Missing {}'.format(curr - last))
    loop.call_later(TIMER_PERIOD, periodic_callback)
    last = curr


if __name__ == '__main__':
    global last
    global loop
    global mem
    service = Service()
    loop = IOLoop.current()
    server = SimpleTestServer(service, loop)
    server.listen(os.environ.get('SIMPLE_SERVICE_PORT', 9966),
                  os.environ.get('SIMPLE_SERVICE_BIND', '0.0.0.0'))
    last = time.time()
    loop.call_later(TIMER_PERIOD, periodic_callback)
    loop.start()

