import socket
import argparse
import time
from struct import pack

def test_associate_controlling_service(args):
    # Create a TCP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((args.server_ip, args.control_port))
    length = pack('!i', len(args.msg))
    sock.send(length)
    sock.send(args.msg)
    print("sent a control message {}".format(args.msg))
    data = []
    result = sock.recv(1024)
    print("result = {}".format(result))
    if 'associated' in result:
        print("TESTCASE: PASS")
        return 0
    else:
        print("TESTCASE: FAILED")
        return -1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--server_ip',
        type=str,
        help='IP address of a requesting server',
        default='10.10.0.1')
    parser.add_argument(
        '--control_port',
        type=int,
        help='Listening port in the requesting server',
        default=9889)
    parser.add_argument(
        '--msg',
        type=str,
        help='Requesting message',
        default='discover MrKatEdge105 UserMaoTest')
    global args
    args = parser.parse_args()
    test_associate_controlling_service(args)


if __name__ == '__main__':
    main()
