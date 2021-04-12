#!/usr/bin/python

import socket
import argparse
import time
from struct import pack
import yaml


def send_control_message(args, message):
    print("Will send a control message", message)
    sock_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_.sendto(message, (args.server_ip, args.control_port))

is_relocated = False
is_migrated = False

def monitor_latency(args, last_elapsed_time):
    global is_relocated
    global is_migrated
    print("last_elapsed_time", last_elapsed_time)
    if last_elapsed_time > 1 and not is_relocated :
        send_control_message(args, 'relocation')
        is_relocated = True
    if last_elapsed_time > 2 and is_relocated:
        send_control_message(args, 'migrate')
        is_migrated = True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--server_ip',
        type=str,
        help='IP address of a requesting server',
        default='localhost')
    parser.add_argument(
        '--port',
        type=int,
        help='Listening port in the requesting server',
        default=9999)
    parser.add_argument(
        '--control_port',
        type=int,
        help='Listening port in the requesting server',
        default=8877)
    parser.add_argument(
        '--imgdir',
        type=str,
        help='Image location/directory',
        default='Rocky.jpg')
    parser.add_argument(
        '--keep',
        help='Continuous asking for the same image sets',
        action='store_true')

    args = parser.parse_args()
    start = time.time()
    elapsed_time = [None] * 100


    # Create a TCP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((args.server_ip, args.port))

    # Thanks for the stackoverflow answer:
    # https://stackoverflow.com/questions/42459499/what-is-the-proper-way-of-sending-a-large-amount-of-data-over-sockets-in-python

    try:
        # Connect to server and send data
        if args.keep:
            while True:
                # Use struct to make sure we have a consistent endiannes on the length
                start = time.time()
                f = open(args.imgdir, 'rb')
                data = f.read()
                f.close()
                length = pack('!i', len(data))
                # sendall to make sure it blocks if there's back-pressure on the socket
                sock.send(length + data)
                print "Sent:     {}".format(len(data))
                data = []
                # Receive data from the server and shut down
                received = sock.recv(1024)
                print("Received: {}".format(received))
                last_elapsed_time = time.time() - start
                monitor_latency(args, last_elapsed_time)
                print("Total elapsed time: {} [s]".format(last_elapsed_time))
                try:
                    msg_json = yaml.safe_load(received)
                    try:
                        general_json = msg_json['general']
                        proc_time = general_json['processTime[ms]']
                        trans_delay = last_elapsed_time*1000 - proc_time
                        print("E2E delay ={} ms".format(trans_delay))
                    except Exception:
                        print("Empty received mesg {}".format(received))
                except yaml.YAMLError:
                    print("error parsing YAML msg {}".format(received))
                elapsed_time.append(last_elapsed_time)
                time.sleep(0)
        else:
            f = open(args.imgdir, 'rb')
            data = f.read()
            f.close()
            # Use struct to make sure we have a consistent endiannes on the length
            length = pack('!i', len(data))
            # sendall to make sure it blocks if there's back-pressure on the socket
            sock.sendall(length)
            sock.sendall(data)
            print "Sent:     {}".format(len(data))
            # Receive data from the server and shut down
            data = []
            received = sock.recv(1024)
            print("Received: {}".format(received))
            last_elapsed_time = time.time() - start
            print("Total elapsed time: {} [s]".format(last_elapsed_time))
            monitor_latency(args, last_elapsed_time)
    finally:
        #sock.close()
        pass

if __name__ == '__main__':
    main()
