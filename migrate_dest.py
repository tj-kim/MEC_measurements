import sys
import time
import socket
import logging
import datetime
import argparse
from subprocess import check_output
import os

import shutil
import docker
import yaml

import Constants
from migrate_node import MigrateNode, MigrateRecord
from migrate_controller import MigrateController
from diff_patch import create_xdelta_patch

""" This file is the migration service running in the destination node.
Whenever the destination receives an instruction from the source node,
it will do according activities, specifically, the following action will
be done:

1. pull the docker base and create the container in the destination node.

2. restore the container based on the transmitted checkpointed files.
"""

def is_port_available(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = 0
    try:
        result = sock.bind(('', port))
    except socket.error:
        print("port {} is already used.".format(port))
    sock.close()
    if result == None:
        print("available port: {}".format(port))
        return True
    else:
        print("port {} is occupied".format(port))
        return False

def find_open_port(start_range=9900, end_range=9999):
    for port in range(start_range, end_range):
        if is_port_available(port):
            return port

def backup_folder(folder):
    folder = folder.rstrip('/')
    if os.path.exists(folder):
        bak = folder + '_bak_dest_' + \
              datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        logging.debug("backup folder: {}-->{}".format(folder, bak))
        shutil.copytree(folder, bak)

class MigrateDestCallback(object):
    def dest_migrate_cb(self, **kwargs):
        pass

    def dest_report_cb(self, report):
        pass

class MigrateDest(MigrateNode):
    def __init__(self, **kwargs):
        super(MigrateDest, self).__init__(**kwargs)
        self.client = docker.from_env()
        self.bind = kwargs.get('bind', "")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", Constants.BETWEEN_EDGES_PORT))
        self.source_addr = None
        self.controller = MigrateController()
        self.dest_cb = MigrateDestCallback()
        self.records = {}
        self.sockets = {}

    def handle_cmd_prepare(self, addr, **kwargs):
        # Restore xdelta
        service = MigrateNode(**kwargs)
        record = MigrateRecord(service=service.get_container_name(),
                                    source_ip=addr[0])
        self.records[service.get_container_name()] = record
        start_premigration = time.time()
        logging.debug("pull for service {}".format(service.get_container_name()))
        handle_pull = self.controller.docker_pull_image(service.container_img,
                                                        wait=False)
        start_xdela_2_3 = time.time()
        logging.info("Restore {} folder".format(service.get_snapshot_pre(3)))
        self.controller.restore_diff(service.get_snapshot_pre(2),
                                     service.get_snapshot_pre(3),
                                     service.get_snapshot_delta(2,3))
        delta = time.time() - start_xdela_2_3
        service.log_time('xdelta_dest_2_3', delta)
        handle_pull.wait()
        delta = time.time() - start_premigration
        service.log_time('premigration', delta)
        record.premigration = delta
        # logging.info("Destination status: ".format(
        #     check_output(['ls', service.get_checkpoint_folder()])))
        new_port = find_open_port(9900, 9999)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('0.0.0.0', new_port))
        self.sockets[service.get_container_name()] = sock
        self.controller.docker_create_container(service.container_img,
                                                service.get_container_name(),
                                                service.container_port,
                                                new_port)

    def handle_cmd_migrate(self, addr, **kwargs):
        service = MigrateNode(**kwargs)
        record = self.records[service.get_container_name()]
        start_migrate = time.time()
        sock = self.sockets[service.get_container_name()]
        service.port = sock.getsockname()[1]
        sock.close()
        if service.method == 'delta':
            start_migrate = time.time()
            # NOTE: Clear any conflict container before create
            self.controller.restore_diff(service.get_snapshot_pre(3),
                                         service.get_snapshot_folder(),
                                         service.get_snapshot_delta())
            delta = time.time() - start_migrate
            service.log_time('xdelta_dest', delta)
            record.xdelta_dest = delta
        start_restore = time.time()
        _, restore_ret_code = self.controller.docker_restore(
            service.get_container_name(),
            service.snapshot,
            service.get_checkpoint_folder())
        delta = time.time() - start_restore
        service.log_time('restore', delta)
        record.restore = delta
        delta = time.time() - start_migrate
        service.log_time('migrate', delta)
        # record.migrate = delta
        # Measure delta memory and pre checkpoint of the new service
        # TODO: Consider using exponential moving average here
        size_delta = \
                self.controller.measure_img_size(service.get_snapshot_delta())
        service.delta_memory = size_delta
        size_precheckpoint = \
                self.controller.measure_img_size(service.get_snapshot_folder())
        service.pre_checkpoint = size_precheckpoint
        if restore_ret_code != 0:
            logging.error("Error while restoring service")
            logging.info("Starting a new container")
            self.controller.docker_start(service.get_container_name())
        self.dest_cb.dest_migrate_cb(**service.get_migrate_service())
        self.dest_cb.dest_report_cb(record)
        self.controller.docker_checkpoint(service.get_container_name(),
                                          service.get_snapshot_name_pre(2),
                                          service.get_checkpoint_folder())
        backup_folder(service.get_checkpoint_folder())


    def restore(self):
        if self.method == 'delta':
            start_ = time.time()
            """
            xdelta_cmd = ['python2', 'diff_patch.py',
                          '--old', self.get_snapshot_pre(),
                          '--new', self.get_snapshot_folder(),
                          '--patch', self.get_snapshot_delta(),
                          '--cmd', 'create_xdelta_patch']
            if self.debug:
                xdelta_cmd.append('--verbose')
            out = check_output(xdelta_cmd)
            logging.info("{}. Output: {}".format(' '.join(xdelta_cmd), out))
            """
            create_xdelta_patch(self.get_snapshot_pre(),
                                self.get_snapshot_folder(),
                                self.get_snapshot_delta(),
                                self.debug)
            delta = time.time() - start_
            self.log_time('xdelta_dest', delta)
            self.record.xdelta_dest = delta
        start_ = time.time()
        self.controller.docker_restore(self.get_container_name(), self.snapshot,
                                       self.get_checkpoint_folder())
        delta = time.time() - start_
        self.log_time('restore', delta)
        self.record.restore = delta
        # Whenever restore successfully, store a new service
        self.dest_cb.dest_migrate_cb(**self.get_migrate_service())
        self.dest_cb.dest_report_cb(self.record)

    def update_migrating_service(self, migrating_service_json):
        migrating_service = yaml.safe_load(migrating_service_json)
        self.snapshot = migrating_service['snapshot']
        self.end_user = migrating_service['end_user']
        self.service_name = migrating_service['service_name']
        self.registry = migrating_service['registry']
        self.ip = migrating_service['ip']
        self.port = int(migrating_service['port'])
        self.container_img = migrating_service['container_img']
        self.container_port = migrating_service['container_port']
        self.dump_dir = migrating_service['dump_dir']
        self.method = migrating_service['method']
        self.server_name = migrating_service['server_name']
        self.ssid = migrating_service['ssid']
        self.bssid = migrating_service['bssid']
        if not is_port_available(self.port):
            self.port = find_open_port(9900, 9999)
            logging.info("Conflict port, find a new port at dest node {}".
                format(self.port))
        else:
            logging.info("port {} is available".format(self.port))
        # send back port self.sock.send
        self.record = MigrateRecord(service='{}{}'.format(self.service_name,
                                                          self.end_user),
                                    source_ip=self.ip)
        self.record.method = self.method
        self.sock.sendto("dest_port {}".format(self.port), self.source_addr)

    def process_line(self, line, addr):
        message = line.split(' ', 1)
        msg_type = message[0]
        try:
            migrating_service_json = yaml.safe_load(message[1])
            if msg_type == 'prepare':
                self.handle_cmd_prepare(addr, **migrating_service_json)
            elif msg_type == 'migrate':
                logging.debug("migrating service {}".format(message[1]))
                self.handle_cmd_migrate(addr, **migrating_service_json)
                # Add premigration record
                # self.record.premigration = delta
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(message[1]))

    def node_main(self):
        # remove all checkpointed dirs
        dirs = os.listdir('/tmp/')
        for d in dirs:
            if Constants.OPENFACE in d or Constants.YOLO in d or\
                Constants.SIMPLE_SERVICE in d:
                folder = os.path.join('/tmp/', d)
                logging.debug("Remove folder {}".format(folder))
                shutil.rmtree(folder, ignore_errors=True)
        while True:
            data, addr = self.sock.recvfrom(1024)
            # NOTE: This approach seem not good enough
            logging.info("Receive command from {} with {}".format(addr, data))
            lines = data.split("\n")
            for line in lines[:-1]:
                self.process_line(line, addr)

if __name__ == '__main__':
    out = check_output(['whoami'])
    if out != 'root\n':
        logging.error('You must run this script under root permission!')
        sys.exit(-1)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--eu',
        type=str,
        help="End-user name. Default: {}".format(Constants.END_USER),
        default = Constants.END_USER)
    parser.add_argument(
        '--service',
        type=str,
        help="Service name which is running in the current edge server.",
        default=Constants.OPENFACE)
    parser.add_argument(
        '--ct',
        type=str,
        help="Container name running in the source edge node is composed by service and end-user name.")
    parser.add_argument(
        '--cttag',
        type=str,
        help="Container tag version.",
        default="06")
    parser.add_argument(
        '--sn',
        type=str,
        help="Snapshot name is to take a snapshot right after starting the fresh container.",
        default="snapshot")
    parser.add_argument(
        '--registry',
        type=str,
        help="Name of Dockerhub or private container registry.",
        default="ngovanmao")
    parser.add_argument(
        '--dump_dir',
        type=str,
        help="Directory for checkpoint and restore in both edge nodes.",
        default="/tmp")
    parser.add_argument('--verbose', action='store_true')

    global args
    args = parser.parse_args()
    args.ct = '{}{}'.format(args.service, args.eu)
    #args.tarball = args.dump_dir + args.sn + ".tar.gz"
    FORMAT = '%(asctime)-15s %(message)s'
    if args.verbose:
        logging.basicConfig(format=FORMAT, level=logging.DEBUG)
    else:
        logging.basicConfig(format=FORMAT, level=logging.INFO)

    client = MigrateDest(snapshot=args.sn,
                         container=args.ct,
                         registry=args.registry,
                         dump_dir=args.dump_dir,
                         verbose=args.verbose,
                         method='rsync' if args.rsync else 'delta')

    client.node_main()
