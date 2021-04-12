""" This file is the migration service running in the source node.

The following steps will be done:

1. Warm up step in checkpoint:
    - send a command to destination to instruct the destination download the base container image,
    - checkpoint and leave the container running,
    - rsync the checkpointed files from source to destination.

2. Checkpoint and stop with two options:
    2.1. checkpoint and use rsync to synchronize the checkpointed files.

        - remove the old checkpointed folder (otherwise docker cannot checkpoint)
        - checkpoint and stop the container
        - rsync the whole folder to the destination folder which was transmitted in step 1.
        - send a command to instruct the destination restore the container.
    2.2. checkpoint and create the delta binary between warm-up checkpointed files and stop checkpointed files.

        - checkpoint and stop the container to a new folder, e.g., called snapshot.
        - transfer all the file except the `*.img` files.
        - using xdelta to create diff binary between the warm-up and stop checkpoint img files.
        - transfer the delta imgs to destination
        - send a command to instruct the destination restore the container.

"""

import os
import sys
import time
import json
import Queue
import socket
import datetime
import argparse
import logging

import shutil
import docker

import Constants
from diff_patch import create_xdelta_diff
from migrate_node import MigrateNode, MigrateRecord
from migrate_controller import MigrateController

def backup_folder_source(folder):
    folder = folder.rstrip('/')
    if os.path.exists(folder):
        bak = folder + '_bak_source_' + \
              datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        logging.debug("backup folder: {}-->{}".format(folder, bak))
        shutil.copytree(folder, bak)

def dummy(**kwargs):
    """
    Unhandled command
    """
    logging.warn("Invalid handle for {}".format(kwargs.get('cmd', '')))

class MigrateSourceCallback(object):
    def source_dirty_rate_cb(self, **kwargs):
        pass

    def source_prepare_cb(self, **kwargs):
        pass

    def source_migrate_cb(self, **kwargs):
        pass

    def source_report_cb(self, report):
        pass

class MigrateSource(MigrateNode):
    """
    .. note::

        This code copy the snapshot folder to <checkpoint dir>/<snapshot>
        folder at destination node. Therefore, the destination node must run first
        to create <checkpoint dir>. Otherwise, this code displays `File not found`
    """

    def __init__(self, **kwargs):
        super(MigrateSource, self).__init__(**kwargs)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client = docker.from_env()
        self.handle = {'delta': self.checkpoint_delta,
                       'rsync': self.checkpoint_rsync}
        self.migrating_service_json = json.dumps(self.get_migrate_service())
        self.migrate_queue = Queue.Queue()
        self.state = 'idle'
        self.cmd_handlers = {'prepare': self.handle_cmd_prepare,
                             'migrate': self.handle_cmd_migrate,
                             'pre_measure': self.handle_cmd_pre_measure,
                             'measure': self.handle_cmd_measure_dirty,
                             '': dummy}
        self.controller = MigrateController()
        self.source_cb = MigrateSourceCallback()
        self.records = {}

    def connect(self):
        self.sock.connect((self.ip, Constants.BETWEEN_EDGES_PORT))

    def request_pull(self):
        logging.info("send msg: pull {} to {} at port {}".
            format(self.migrating_service_json, self.ip,
            Constants.BETWEEN_EDGES_PORT))
        self.sock.sendto("pull {}\n".format(self.migrating_service_json),
                         (self.ip, Constants.BETWEEN_EDGES_PORT))

    def request_migrate(self):
        logging.info("send msg: migrate {} to {} at port {}".
            format(self.migrating_service_json, self.ip,
                Constants.BETWEEN_EDGES_PORT))
        self.sock.sendto("migrate {}\n".format(self.migrating_service_json),
                         (self.ip, Constants.BETWEEN_EDGES_PORT))

    def create_checkpoint_leave_running(self, suffix):
        self.controller.docker_checkpoint(self.get_container_name(),
                        '{}{}'.format(self.snapshot, suffix),
                        self.get_checkpoint_folder())
        logging.info(os.listdir(self.get_snapshot_pre()))

    def create_checkpoint(self, suffix=''):
        self.controller.docker_checkpoint(self.get_container_name(),
                        '{}{}'.format(self.snapshot, suffix),
                        self.get_checkpoint_folder(), leave_running=False)
        logging.info(os.listdir(self.get_snapshot_folder()))

    def is_same_container(self, name):
        return self.get_container_name() == name

    def prepare_migration(self):
        start_ = time.time()
        containers = self.client.containers.list(all=True,
                           filters={'name': self.get_container_name()})
        if len(containers) == 0:
            logging.error("Cannot found the container, create it first!")
            raise RuntimeError('Container not found!')
        # Check if the continer is running
        container = containers[0]
        if container.status != 'running':
            logging.error("container exited!")
            raise RuntimeError('Container exited!')
        shutil.rmtree(self.get_checkpoint_folder(), ignore_errors=True)
        shutil.rmtree(self.get_snapshot_folder(), ignore_errors=True)
        shutil.rmtree(self.get_snapshot_pre(), ignore_errors=True)
        shutil.rmtree(self.get_snapshot_delta(), ignore_errors=True)
        self.create_checkpoint_leave_running('_pre')
        delta = time.time() - start_
        self.log_time('pre-checkpoint', delta)
        self.record.pre_checkpoint = delta
        start_ = time.time()
        self.controller.rsync(self.get_snapshot_pre(),
                              self.user, self.ip, self.get_checkpoint_folder())
        # Measure the whole folder with byte unit
        delta = time.time() - start_
        self.log_time('pre-rsync', delta)
        self.record.pre_rsync = delta
        size_pre_rsync = self.controller.measure_img_size(
            self.get_snapshot_pre())
        self.log_size('pre-rsync', size_pre_rsync)
        self.record.checkpoint_size = size_pre_rsync

    def checkpoint_delta(self):
        start_ = time.time()
        self.create_checkpoint()
        delta = time.time() - start_
        self.log_time('checkpoint', delta)
        self.record.checkpoint = delta
        start_ = time.time()
        self.controller.rsync(self.get_checkpoint_folder(), self.user, self.ip,
                              self.get_checkpoint_folder(), include='*.tar.gz.img',
                              exclude='*.img')
        delta = time.time() - start_
        self.log_time('rsync', delta)
        self.record.rsync = delta
        size_rsync = self.controller.measure_img_size(
            self.get_snapshot_folder(),
            exclude='*.img')
        self.log_size('rsync', size_rsync)
        self.record.size_rsync = size_rsync
        start_ = time.time()
        os.mkdir(self.get_snapshot_delta())
        """
        xdelta_cmd = ['python2', 'diff_patch.py',
                      '--old', self.get_snapshot_pre(),
                      '--new', self.get_snapshot_folder(),
                      '--patch', self.get_snapshot_delta(),
                      '--verbose',
                      '--cmd', 'create_xdelta_diff']
        if self.debug:
            xdelta_cmd.append('--verbose')
        out = check_output(xdelta_cmd)
        logging.debug('{}. Output: {}'.format(' '.join(xdelta_cmd), out))
        """
        create_xdelta_diff(self.get_snapshot_pre(),
                           self.get_snapshot_folder(),
                           self.get_snapshot_delta(),
                           self.debug)
        delta = time.time() - start_
        self.log_time('xdelta_source', delta)
        self.record.xdelta_source = delta
        start_ = time.time()
        self.controller.rsync(self.get_snapshot_delta(),
                              self.user, self.ip, self.get_checkpoint_folder())
        delta = time.time() - start_
        self.log_time('final_rsync', delta)
        self.record.final_rsync = delta
        size_final_rsync = self.controller.measure_img_size(
            self.get_snapshot_delta())
        self.log_size('final_rsync', size_final_rsync)
        self.record.size_final_rsync = size_final_rsync

    def checkpoint_rsync(self):
        start_ = time.time()
        containers = self.client.containers.list(all=True,
                           filters={'name': self.get_container_name()})
        if len(containers) == 0:
            logging.error("Cannot found the container!")
            raise RuntimeError('Container not found!')
        container = containers[0]
        if container.status != 'running':
            logging.error("container exited!")
            raise RuntimeError('Container exited!')
        shutil.rmtree(self.get_snapshot_folder(), ignore_errors=True)
        self.create_checkpoint()
        delta = time.time() - start_
        self.log_time('checkpoint', delta)
        self.record.checkpoint = delta
        start_ = time.time()
        self.controller.rsync(self.get_snapshot_folder(), self.user, self.ip,
                              self.get_checkpoint_folder())
        delta = time.time() - start_
        self.log_time('rsync', delta)
        self.record.rsync = delta
        size_rsync = self.controller.measure_img_size(
            self.get_snapshot_folder())
        self.log_size('rsync', size_rsync)
        self.record.size_rsync = size_rsync

    def reserve_dest_resource(self):
        self.connect() # Connect to server
        self.request_pull()
        data, dest_addr = self.sock.recvfrom(4096)
        logging.info("return message from migrate_dest {}".format(data))
        remote_port = data.split(" ", 1)[1]
        return remote_port

    def handle_cmd_pre_measure(self, kwargs):
        self.state = 'pre_measure'
        logging.info('Start pre-measure checkpoint')
        # This first checkpoint
        service = MigrateNode(**kwargs)
        self.controller.docker_verify(service)
        self.controller.docker_checkpoint(service.get_container_name(),
                                          service.get_snapshot_name_pre(1),
                                          service.get_checkpoint_folder())

    def handle_cmd_measure_dirty(self, kwargs):
        self.state = 'measure'
        # Second checkpoint
        logging.info('Start measure dirty rate')
        service = MigrateNode(**kwargs)
        start_checkpoint = time.time()
        self.controller.docker_checkpoint(service.get_container_name(),
                                          service.get_snapshot_name_pre(2),
                                          service.get_checkpoint_folder())
        delta = time.time() - start_checkpoint
        service.log_time('time_checkpoint', delta)
        kwargs['time_checkpoint'] = delta
        # Compute delta
        start_ = time.time()
        self.controller.compute_diff(service.get_snapshot_pre(1),
                                     service.get_snapshot_pre(2),
                                     service.get_snapshot_delta(1,2))
        delta = time.time() - start_
        service.log_time("time_delta", delta)
        kwargs['time_xdelta'] = delta
        # Measure delta
        dirty=self.controller.measure_img_size(service.get_snapshot_delta(1,2))
        pre_migration=self.controller.measure_img_size(service.get_snapshot_pre(2))
        kwargs['delta_memory'] = dirty
        kwargs['pre_checkpoint'] = pre_migration
        self.source_cb.source_dirty_rate_cb(**kwargs)

    def handle_cmd_prepare(self, data):
        self.state = 'prepare'
        logging.info('Start prepare migration')
        start_prepare = time.time()
        service = MigrateNode(**data)
        record = MigrateRecord(dest_ip=service.ip,
                               service=service.get_container_name())
        self.controller.open_ssh_session(service.user, service.ip)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.records[service.get_container_name()] = record
        if self.method != 'delta':
            return
        # Send pre2
        handle_pre2 = self.controller.rsync(service.get_snapshot_pre(2),
                                            service.user, service.ip,
                                            service.get_checkpoint_folder(),
                                            wait=False)
        size_pre_rsync = self.controller.measure_img_size(
            service.get_snapshot_pre(2))
        service.log_size('size_pre_rsync', size_pre_rsync)
        record.size_pre_rsync = size_pre_rsync
        # Checkpoint
        start_pre_cp = time.time()
        _, ret_code = self.controller.docker_checkpoint(
            service.get_container_name(),
            service.get_snapshot_name_pre(3),
            service.get_checkpoint_folder())
        if ret_code != 0:
            logging.error("Error occured while checkpoint container {}".\
                          format(service.get_container_name()))
        delta = time.time() - start_pre_cp
        service.log_time('pre_checkpoint', delta)
        record.pre_checkpoint = delta
        # Send checkpoint file to reduce the pre-migrate time
        # Exclude *.img to prevent transmitting heavy files
        handle_pre3 = self.controller.rsync(service.get_snapshot_pre(3),
                                            service.user, service.ip,
                                            service.get_checkpoint_folder(),
                                            include='*.tar.gz.img',
                                            exclude='*.img',
                                            wait=False)
        # Compute delta
        start_xdelta = time.time()
        self.controller.compute_diff(service.get_snapshot_pre(2),
                                     service.get_snapshot_pre(3),
                                     service.get_snapshot_delta(2,3))
        delta = time.time() - start_xdelta
        service.log_time('xdelta_source_2_3', delta)
        size_rsync_2_3 = self.controller.measure_img_size(
            service.get_snapshot_delta(2,3))
        service.log_size('xdelta_source_2_3', size_rsync_2_3)
        start_rsync_2_3 = time.time()
        self.controller.rsync(service.get_snapshot_delta(2,3),
                              service.user, service.ip,
                              service.get_checkpoint_folder())
        delta = time.time() - start_rsync_2_3
        service.log_time('rsync_2_3', delta)
        # Waiting for rsync commands
        ret = handle_pre3.wait() # Log this time
        logging.info("rsync pre3 command return code: {}, stdout: {}".\
                     format(ret, handle_pre3.communicate()))
        ret = handle_pre2.wait() # Log this time
        logging.info("rsync pre2 command return code: {} , stdout: {}".\
                     format(ret, handle_pre2.communicate()))
        delta = time.time() - start_prepare
        service.log_time('pre_rsync', delta)
        service.log_time('prepare', delta)
        record.prepare = delta
        self.source_cb.source_prepare_cb(**data)
        # Notify the destination
        self.sock.sendto("prepare {}\n".format(service.get_migrate_service()),
                         (service.ip, Constants.BETWEEN_EDGES_PORT))

    def handle_cmd_migrate(self, data):
        self.state = 'migrate'
        logging.info('Start migrate')
        # if self.state != 'prepare':
        #     logging.warn("Invalid state: {} ignore this command".\
        #                  format(self.state))
        #     return
        service = MigrateNode(**data)
        record = self.records[service.get_container_name()]
        start = time.time()
        logging.info("Send msg: migrate {} to {} at port {}".\
                     format(service.get_migrate_service(), service.ip,
                     Constants.BETWEEN_EDGES_PORT))
        # Start checkpoint and stop the service
        start_checkpoint = time.time()
        _, ret_code = self.controller.docker_checkpoint(
            service.get_container_name(),
            service.snapshot,
            service.get_checkpoint_folder(),
            leave_running=False)
        if ret_code != 0:
            logging.error("Error occured while checkpoint container {}".\
                          format(service.get_container_name()))
        delta = time.time() - start_checkpoint
        service.log_time('checkpoint', delta)
        record.checkpoint = delta
        handle_snapshot = self.controller.rsync(service.get_snapshot_folder(),
                                                service.user, service.ip,
                                                service.get_checkpoint_folder(),
                                                include="*.tar.gz.img",
                                                exclude="*.img", wait=False)
        start_xdelta = time.time()
        is_parallel = True
        self.controller.compute_diff(service.get_snapshot_pre(3),
                                     service.get_snapshot_folder(),
                                     service.get_snapshot_delta(),
                                     is_parallel)
        delta = time.time() - start_xdelta
        service.log_time('xdelta_source', delta)
        record.xdelta_source = delta
        start_final_rsync = time.time()
        self.controller.rsync(service.get_snapshot_delta(), service.user,
                              service.ip, service.get_checkpoint_folder())
        delta = time.time() - start_final_rsync
        service.log_time('final_rsync', delta)
        record.final_rsync = delta
        ret = handle_snapshot.wait() # Log this time
        logging.info("rsync small files snapshot return: {} , stdout: {}".\
                     format(ret, handle_snapshot.communicate()))
        self.sock.sendto("migrate {}\n".format(service.get_migrate_service()),
                         (service.ip, Constants.BETWEEN_EDGES_PORT))
        delta = time.time() - start
        service.log_time('migrate', delta)
        record.migrate = delta
        self.sock.close()
        size_final_rsync = self.controller.measure_img_size(
            service.get_snapshot_delta())
        service.log_size('size_final_rsync', size_final_rsync)
        record.size_final_rsync = size_final_rsync
        # Waiting for rsync commands
        self.source_cb.source_migrate_cb(**data)
        self.source_cb.source_report_cb(record)
        # Remove old checkpoints
        backup_folder_source(service.get_checkpoint_folder())
        shutil.rmtree(service.get_checkpoint_folder(), ignore_errors=True)
        self.controller.close_ssh_session()

    def node_main(self):
        # remove all ssh-root files
        files = os.listdir('/root/.ssh/')
        for f in files:
            if 'ssh-root' in f:
                rf = os.path.join('/root/.ssh/', f)
                logging.debug("Remove old ssh-master {}".format(rf))
                os.remove(rf)
        while True:
            new_cmd = self.migrate_queue.get(True)
            self.cmd_handlers.get(new_cmd[0], dummy)(new_cmd[1])
            self.migrate_queue.task_done()

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
        help="Container name running in the source edge node=service+end_user.")
    parser.add_argument(
        '--cttag',
        type=str,
        help="Container tag version.",
        default="latest")
    parser.add_argument(
        '--sn',
        type=str,
        help="Snapshot name is to take a snapshot right after starting the \
        fresh container.",
        default="snapshot")
    parser.add_argument(
        '--registry',
        type=str,
        help="Name of Dockerhub or private container registry.",
        default="ngovanmao")
    parser.add_argument(
        '--dest_user',
        type=str,
        help="User name of the next edge server.",
        default="root")
    parser.add_argument(
        '--dest_ip',
        type=str,
        help="IP address of the next edge server. Default: 192.168.0.105",
        default="192.168.0.105")
    parser.add_argument(
        '--dest_port',
        type=int,
        help="Port of the next edge server. Default: 5678",
        default=5678)
    parser.add_argument(
        '--dump_dir',
        type=str,
        help="Directory for checkpoint and restore in both edge nodes.\
            Default: /tmp/",
        default="/tmp")
    parser.add_argument(
        '--cimg',
        help="Full container image.",
        type=str)
    parser.add_argument(
        '--verbose',
        help="Verbose print debug.",
        action='store_true')
    parser.add_argument(
        '--rsync',
        help="using rsync option instead of xdelta as default.",
        action='store_true')

    args = parser.parse_args()
    args.ct = '{}{}'.format(args.service, args.eu)
    args.cimg = '{}/{}:{}'.format(args.registry, args.ct, args.cttag)
    # NOTE: logging module provides more flexible ways to print out
    # message, such as print to file and formated message
    FORMAT = '%(asctime)-15s %(levelname)s %(message)s'
    if args.verbose:
        logging.basicConfig(format=FORMAT, level=logging.DEBUG)
    else:
        logging.basicConfig(format=FORMAT, level=logging.INFO)

    logging.info("container image: {}".format(args.cimg))
    client = MigrateSource(snapshot=args.sn,
                           container=args.ct,
                           registry=args.registry,
                           user=args.dest_user,
                           ip=args.dest_ip,
                           port=args.dest_port,
                           container_img=args.cimg,
                           dump_dir=args.dump_dir,
                           debug=args.verbose,
                           method='rsync' if args.rsync else 'delta')

    client.node_main()
