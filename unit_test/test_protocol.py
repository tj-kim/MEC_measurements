import pytest
import mock
import threading
import socket
import time
from .. import edge_protocol as proto

def test_prepare_json():
    assert '\x00\x00\x00\x0amonitor {}' == proto.prepare_msg_json('monitor', {})

def test_prepare():
    assert '\x00\x00\x00\x0bmonitor 123' == proto.prepare_msg('monitor', '123')

server_mock = mock.Mock()
TEST_PORT = 10000

class ServerForTest(proto.EdgeTCPServer):
    def on_connected(self, *args):
        server_mock.on_connected()

    def on_msg(self, conn, msg):
        server_mock.on_msg()

    def on_closed(self):
        server_mock.on_closed()

on_test_cb = mock.MagicMock(return_value="hello")

class ClassForTestProtocol(proto.ProtocolNode):
    def __init__(self):
        super(ClassForTestProtocol, self).__init__()
        self.add_callback('test', on_test_cb)

@pytest.fixture
def tcpserver():
    s = ServerForTest("", TEST_PORT)
    thrd = threading.Thread(target=s.start_server_loop)
    thrd.setDaemon(True)
    thrd.start()
    return s

def test_edge_tcp(tcpserver):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(('127.0.0.1', TEST_PORT))
    sock.sendall(proto.prepare_msg('dummy', 'hello'))
    time.sleep(0.1)
    sock.close()
    time.sleep(0.1)
    assert server_mock.on_connected.called
    assert server_mock.on_closed.called
    assert server_mock.on_msg.called

def test_protocol_class():
    p = ClassForTestProtocol()
    res = p.get_message('test hello')
    assert res == 'hello'
    on_test_cb.assert_called_with('hello')

def test_tcp_client():
    client = proto.EdgeTCPClient('127.0.0.1', TEST_PORT)
    res = client.send_msg("test hello")
    client.close_socket()
    assert res == ''

