#!/usr/bin/env python

"""This is a simple TCP server to simulate a CPU-bound service.

The server receives requests from users and return the sum of all
prime numbers up to PRIME, which is an environment
variable. Currently, the server supports only one core.

"""
import os
import json
import math
import time
import asyncio
import concurrent.futures
import functools
import struct

# Number of cores used by each request. `0` means each request uses
# all cores.
NUM_CORES = int(os.getenv('NUM_CORES', 1))

# Prime target
PRIME = int(os.getenv('FIND_PRIME', '200000'))

def is_prime(n):
    if n < 3:
        return True
    elif n % 2 == 0:
        return False

    sqrt_n = int(math.floor(math.sqrt(n)))
    for i in range(3, sqrt_n + 1, 2):
        if n % i == 0:
            return False
    return True

def cpu_bound():
    return list(filter(is_prime, (range(PRIME))))

def done_cb(transport, start_time, transfer_time, cnt, future):
    proc_time = time.time() - start_time
    ret_msg = {'list':sum(future.result()),
               'general': {
                   'processTime[ms]': proc_time,
                   'transferTime[ms]': transfer_time,
                   'indexServer': cnt
               }}
    transport.write(json.dumps(ret_msg).encode())

class TCPServer(asyncio.Protocol):
    def connection_made(self, transport):
        """Initializes this connection."""
        peername = transport.get_extra_info('peername')
        print('Connection from {}'.format(peername))
        self.transport = transport
        self.byte_to_read = 0
        self.buf = b''
        self.state = 'wait_len'
        self.cnt = 0
        self.loop = asyncio.get_event_loop()
        self.start_time = 0

    def data_received(self, data):
        """Handles this data stream.

        This function use state machine to handle the protocol.
        """
        print("Receive: {} bytes".format(len(data)))
        while len(data) != 0:
            # While not consume all data
            if self.byte_to_read == 0:
                # Waiting for length
                self.start_time = time.time()
                if len(data) < 4 - len(self.buf):
                    # Consume all data
                    self.buf += data
                    data = b''
                else:
                    len_buf = len(self.buf)
                    self.buf += data[:4 - len_buf]
                    data = data[4-len_buf:]
                    (self.byte_to_read,) = struct.unpack('!i', self.buf)
                    self.buf = b''
            elif len(data) < self.byte_to_read:
                # Save all data to buffer
                self.buf += data
                self.byte_to_read -= len(data)
                data = b''
            else:
                # Read remain bytes
                self.buf += data[:self.byte_to_read]
                # Do something with data
                # Consume data
                self.buf = b''
                if len(data) > self.byte_to_read:
                    data = data[self.byte_to_read:]
                else:
                    data = b''
                transfer_time = time.time() - self.start_time
                self.byte_to_read = 0
                self.cnt += 1
                start_time = time.time()
                with concurrent.futures.ProcessPoolExecutor(max_workers=1) as pool:
                    # It is preferable to run CPU-bound operations in
                    # a process pool because it can block the event
                    # loop.
                    result = self.loop.run_in_executor(
                        pool, cpu_bound)
                    cb = functools.partial(done_cb,
                                           self.transport, start_time,
                                           transfer_time, self.cnt)
                    result.add_done_callback(cb)

def main(bind, port):
    loop = asyncio.get_event_loop()
    coro = loop.create_server(TCPServer, bind, port)
    server = loop.run_until_complete(coro)
    print('Server started')
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()

if __name__ == '__main__':
    PORT = os.environ.get('SIMPLE_SERVICE_PORT', 9966)
    BIND = os.environ.get('SIMPLE_SERVICE_BIND', '0.0.0.0')
    main(BIND, PORT)
