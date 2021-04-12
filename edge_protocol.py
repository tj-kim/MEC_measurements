import logging
import socket
import struct
import json
from threading import Thread

class ProtocolServer(object):
    """This is an abstract class for server. The subclasses must implement these
    function.
    """
    def start_listen(self):
        raise NotImplementedError

    def on_connected(self, *args):
        raise NotImplementedError

    def on_closed(self):
        raise NotImplementedError

    def on_msg(self, conn, msg):
        raise NotImplementedError

    def start_server_loop(self):
        raise NotImplementedError

class ProtocolClient(object):
    def __init__(self):
        pass

    def send_msg(self, msg):
        raise NotImplementedError

    def close_socket(self):
        raise NotImplementedError

class EdgeTCPServer(ProtocolServer):
    """NOTE: For test purpose, just use multiple threads to handle multiples
    clients. We will change to non-block I/O for better scalability.
    """
    def __init__(self, bind, port, limit=16):

        super(EdgeTCPServer, self).__init__()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((bind, port))
        self.port = port
        self.sock.listen(limit)
        self.clients = []

    def client_thread(self, conn, ip, port):
        self.on_connected(conn, ip, port)
        buf = ''
        while len(buf) < 4:
            buf += conn.recv(4 - len(buf))
        length = struct.unpack('!i', buf)[0]
        signal_data = ''
        while len(signal_data) < length:
            to_read = length - len(signal_data)
            signal_data += conn.recv(4096 if to_read > 4096 else to_read)
        self.on_msg(conn, signal_data)
        conn.shutdown(socket.SHUT_RDWR)
        conn.close()
        self.on_closed()

    def start_server_loop(self):
        while True:
            (conn, (ip, port)) = self.sock.accept()
            new_client = Thread(target=self.client_thread, args=(conn, ip, port))
            new_client.setDaemon(True)
            new_client.start()
            # self.clients.append(new_client)

    def stop_server(self):
        self.sock.shutdown(socket.SHUT_RD)
        self.sock.close()

class EdgeTCPClient(ProtocolClient):
    def __init__(self, server_ip, server_port):
        super(EdgeTCPClient, self).__init__()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(100)
        self.sock.connect((server_ip, server_port))

    def send_msg(self, msg):
        length = struct.pack('!i', len(msg))
        self.sock.send(length)
        self.sock.send(msg)
        result = self.sock.recv(1024)
        return result

    def close_socket(self):
        self.sock.close()


class ProtocolNode(object):
    # Static variables
    COMMAND_IDX = 0
    PAYLOAD_IDX = 1

    def __init__(self):
        self.cb = {}

    def add_callback(self, msg_type, func):
        self.cb[msg_type] = func

    def get_message(self, line):
        msg = line.split(' ', 1)
        try:
            return self.cb[msg[self.COMMAND_IDX]](msg[self.PAYLOAD_IDX])
        except KeyError:
            logging.warning("Unhandled command: {}".format(line))
            return ""

def prepare_msg(msg_type, msg):
    msg = '{} {}'.format(msg_type, msg)
    return struct.pack('!i', len(msg)) + msg.encode()

# Prepare message from JSON object
def prepare_msg_json(msg_type, obj):
    return prepare_msg(msg_type, json.dumps(obj, separators=(',',':')))
