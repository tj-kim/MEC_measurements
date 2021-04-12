#!/usr/bin/env python
import time
import Queue
import logging
import argparse
import sys
import json
import traceback
from subprocess import check_output
from threading import Thread

import yaml
import docker

import Constants
from mqtt_protocol import MqttClient
from migrate_node import MigrateNode, MigrateRecord
from migrate_source import MigrateSource, MigrateSourceCallback
from migrate_dest import MigrateDest, MigrateDestCallback
from network_monitor import NetworkMonitor
from server_monitor import ServerMonitor
from container_monitor import ContainerMonitor
from edge_services import EdgeServices
from edge_servers import EdgeServers
from utilities import (find_my_ip,
                       get_hostname,
                       get_ap_ssid,
                       get_json_from_object)
from utilities import (check_swap_file,
                       get_container_for_service,
                       find_open_port)
from utilities import handle_exception
from discovery_edge import DiscoveryYaml

ready = False


def wait_ready():
    while not ready:
        time.sleep(1)


def source_migration_handler(verbose, source_cb, migrate_queue):
    wait_ready()
    migrator_source = MigrateSource(debug=verbose)
    migrator_source.migrate_queue = migrate_queue
    migrator_source.source_cb = source_cb
    try:
        migrator_source.node_main()
    except Exception:
        logging.exception(traceback.format_exc())


def dest_migration_handler(verbose, dest_cb):
    wait_ready()
    migrator_dest = MigrateDest(debug=verbose)
    migrator_dest.dest_cb = dest_cb
    try:
        migrator_dest.node_main()
    except Exception:
        logging.exception(traceback.format_exc())


def network_monitor_handler(my_report_method, queue, broker_ip, conf):
    wait_ready()
    logging.info("start test network monitor using netperf")
    netMon = NetworkMonitor(report=my_report_method, conf=conf)
    netMon.queue = queue
    netMon.remote = broker_ip
    try:
        netMon.main_monitor()
    except Exception:
        logging.exception(traceback.format_exc())


def server_monitor_handler(my_report_method, conf_file):
    wait_ready()
    logging.info("Start edge server monitor")
    server_mon = ServerMonitor(20, report=my_report_method, conf=conf_file)
    try:
        server_mon.main_monitor()
    except Exception:
        logging.error(traceback.format_exc())


def container_monitor_handler(my_report_method, queue):
    wait_ready()
    logging.info("Start container monitor")
    container_mon = ContainerMonitor(report=my_report_method)
    container_mon.queue = queue
    try:
        container_mon.main_monitor()
    except Exception:
        logging.error(traceback.format_exc())


class ControllerServer(MqttClient, MigrateSourceCallback, MigrateDestCallback):
    def __init__(self, broker_ip, broker_port, **kwargs):
        # bs_name = get_ap_ssid()
        bs_name = kwargs.get('bs_name', None)
        distance = kwargs.get('distance')
        self.server_info = {'ip': find_my_ip(broker_ip),
                            'server_name': get_hostname(),
                            'distance': distance}
        if bs_name is not None:
            self.server_info['bs'] = bs_name
            self.server_info['bs_x'] = kwargs.get('bs_x', None)
            self.server_info['bs_y'] = kwargs.get('bs_y', None)
        super(ControllerServer, self).__init__(
            client_id=self.server_info['server_name'],
            clean_session=True,
            broker_ip=broker_ip,
            broker_port=broker_port,
            keepalive=60,
            lwt_topic='{}/{}'.format(Constants.LWT_EDGE,
                                     self.server_info['server_name']))
        self.my_deploy = '{}/{}'.format(Constants.DEPLOY,
                                        self.server_info['server_name'])
        self.my_pre_migrate = '{}/{}'.format(Constants.PRE_MIGRATE,
                                             self.server_info['server_name'])
        self.my_migrate = '{}/{}'.format(Constants.MIGRATE,
                                         self.server_info['server_name'])
        self.my_destroy = '{}/{}'.format(Constants.DESTROY,
                                         self.server_info['server_name'])
        self.neighbor_edges = '{}/+'.format(Constants.LWT_EDGE)
        self.message_callback_add(self.my_deploy, self.process_deploy)
        self.message_callback_add(Constants.UPDATED_SERVERS,
                                  self.process_updated_servers)
        self.message_callback_add(self.my_pre_migrate,
                                  self.process_pre_migrate)
        self.message_callback_add(self.my_migrate, self.process_migrate)
        self.message_callback_add(self.my_destroy, self.process_destroy)
        self.message_callback_add(self.neighbor_edges,
                                  self.process_neighbor_off)
        self.message_callback_add(Constants.MONITOR_SERVICE_ALL,
                                  self.process_monitor_service)
        self.edge_services = EdgeServices()
        self.my_neighbors = EdgeServers()
        self.mon_queue_container = Queue.Queue()
        self.mon_queue_network = Queue.Queue()
        self.source_queue = Queue.Queue()
        self.rho = kwargs.get('rho', 1)
        self.phi = kwargs.get('phi', 1)
        self.server_info['rho'] = self.rho
        self.server_info['phi'] = self.phi

    def on_connect(self, client, userdata, flag, rc):
        logging.info("Connected to broker with result code {}".format(rc))
        # subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe([(self.my_deploy, 1), (self.my_migrate, 1),
                          (self.neighbor_edges, 1), (self.my_destroy, 1),
                          (Constants.UPDATED_SERVERS, 1),
                          (self.my_pre_migrate, 1)])

    def register_to_centre(self):
        msg = '{}'.format(self.server_info)
        self.publish(Constants.REGISTER, msg)

    def start_edge_service(self, service_json):
        service_name = service_json[Constants.SERVICE_NAME]
        end_user = service_json[Constants.END_USER]
        ap_ssid = service_json[Constants.ASSOCIATED_SSID]
        ap_bssid = service_json[Constants.ASSOCIATED_BSSID]
        method = 'delta'
        if service_json[Constants.MIGRATE_METHOD] == \
           Constants.NON_LIVE_MIGRATION:
            method = 'rsync'
        docker_client = docker.from_env()
        container_img, container_port = get_container_for_service(service_name)
        container_name = service_name + end_user
        edge_service = MigrateNode(service_name=service_name,
                                   end_user=end_user,
                                   ip=self.server_info['ip'],
                                   server_name=self.server_info[Constants.SERVER_NAME],
                                   ssid=ap_ssid,
                                   bssid=ap_bssid,
                                   port=find_open_port(9900, 9999),
                                   container_img=container_img,
                                   container_port=container_port,
                                   method=method)
        logging.info("check container name {}".format(container_name))
        try:
            container = docker_client.containers.get(container_name)
            logging.info("Detect the container {} for user{}.".
                         format(container_name, end_user))
            if container.status == 'running':
                lookup_service = self.edge_services.get_service(end_user,
                                                                service_name)
                if lookup_service is not None:
                    logging.debug("found available service ....{}".
                                  format(lookup_service.__dict__))
                    edge_service = lookup_service
                else:
                    # old container before edge_controller starts.
                    container.remove(force=True)
                    try:
                        container = docker_client.containers.run(
                            container_img,
                            auto_remove=True,
                            detach=True,
                            name=container_name,
                            ports={
                                '{}/tcp'.format(container_port):
                                edge_service.port
                            })
                        logging.debug("adding service ....{}".
                                      format(edge_service.__dict__))
                        self.edge_services.add_service(edge_service)
                        self.subscribe_monitor_service(edge_service.end_user)
                        # Shows all docker services
                        out = check_output(['docker', 'ps', '-a'])
                        logging.debug("Docker status: {}".format(out))
                    except Exception:
                        logging.exception("Cannot create and run a"
                                          " docker container {}"
                                          .format(container_img))
                        edge_service = None
            else:
                # exited
                container.remove(force=True)
                try:
                    container = docker_client.containers.run(
                        container_img,
                        auto_remove=True,
                        detach=True,
                        name=container_name,
                        ports={'{}/tcp'.format(container_port):
                               edge_service.port})
                    logging.debug("adding service ....{}"
                                  .format(edge_service.__dict__))
                    self.edge_services.add_service(edge_service)
                    self.subscribe_monitor_service(edge_service.end_user)
                    # Shows all docker services
                    out = check_output(['docker', 'ps', '-a'])
                    logging.debug("Docker status: {}".format(out))
                except Exception:
                    logging.exception("Cannot create and run a docker"
                                      " container {}".
                                      format(container_img))
                    edge_service = None
        except docker.errors.NotFound:
            print("Not available docker container_name {}.\
                Try run a new one.".format(container_name))
            try:
                container = docker_client.containers.run(
                    container_img,
                    auto_remove=True,
                    detach=True,
                    name=container_name,
                    ports={'{}/tcp'.format(container_port):
                           edge_service.port})
                logging.debug("adding service ....{}"
                              .format(edge_service.__dict__))
                self.edge_services.add_service(edge_service)
                self.subscribe_monitor_service(edge_service.end_user)
                # Shows all docker services
                out = check_output(['docker', 'ps', '-a'])
                logging.debug("Docker status: {}".format(out))
            except Exception:
                logging.exception("Cannot create and run a docker"
                                  " container {}".format(container_img))
                edge_service = None
        self.mon_queue_container.put(self.edge_services.services)
        return edge_service

    def subscribe_monitor_service(self, end_user):
        topic = '{}/{}'.format(Constants.MONITOR_SERVICE, end_user)
        logging.debug("subscribe topic {}".format(topic))
        self.subscribe([(topic, 1)])

    def unsubscribe_monitor_service(self, end_user):
        topic = '{}/{}'.format(Constants.MONITOR_SERVICE, end_user)
        logging.debug("Unsubscribe topic {}".format(topic))
        self.unsubscribe(topic)

    def process_pre_migrate(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        payload = {}
        try:
            service_json = yaml.safe_load(msg)
            logging.info("service {}".format(service_json))
            pre_mig_service = MigrateNode(**service_json)
            if service_json[Constants.SERVER_NAME] != \
               self.server_info[Constants.SERVER_NAME]:
                # Handle migration to a different server
                logging.info("Start pre-migrating a service to {}".
                             format(pre_mig_service.ip))
                local_service = self.edge_services.get_service(
                    pre_mig_service.end_user,
                    pre_mig_service.service_name)
                if local_service is None:
                    logging.warn("Cannot prepare {},"
                                 " service not found".
                                 format(pre_mig_service.get_container_name()))
                    # NOTE: Should we need to notify the centralized controller
                    # about this error?
                    return
                pre_mig_service = MigrateNode(**service_json)
                pre_mig_service.time_xdelta = local_service.time_xdelta
                pre_mig_service.time_checkpoint = local_service.time_checkpoint
                pre_mig_service.delta_memory = local_service.delta_memory
                pre_mig_service.pre_checkpoint = local_service.pre_checkpoint
                # Prepare
                self.source_queue.put(('prepare',
                                       pre_mig_service.get_migrate_service()))
                return
            topic = '{}/{}'.format(Constants.PRE_MIGRATED,
                                   pre_mig_service.end_user)
            payload = json.dumps(service_json)
            self.publish(topic, payload)
            logging.info("Publish topic: {}, payload: {}".format(topic,
                                                                 payload))
            # self.mon_queue_container.put(self.edge_services.services)
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_migrate(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        # payload = {}
        try:
            migrating_service_json = yaml.safe_load(msg)
            logging.info("service {}".format(migrating_service_json))
            migrating_service = MigrateNode(**migrating_service_json)
            if migrating_service_json[Constants.SERVER_NAME] != \
               self.server_info[Constants.SERVER_NAME]:
                # Handle migration to a different server
                # Update local information
                logging.info("Start migrating a service to {}".
                             format(migrating_service.ip))
                local_service = self.edge_services.get_service(
                    migrating_service.end_user,
                    migrating_service.service_name)
                if local_service is None:
                    logging.warning(
                        "Cannot migrate {}, service not found".
                        format(migrating_service.get_container_name()))
                    # NOTE: Should we need to notify the centralized controller
                    # about this error?
                    return
                # Copy the request number to the new service
                migrating_service.time_xdelta = local_service.time_xdelta
                migrating_service.time_checkpoint = \
                    local_service.time_checkpoint
                migrating_service.delta_memory = local_service.delta_memory
                migrating_service.pre_checkpoint = local_service.pre_checkpoint
                migrating_service.request = local_service.request
                self.source_queue.put(
                    ('migrate', migrating_service.get_migrate_service()))
                # Waiting for the migration process in `source_migrate_cb`
                self.mon_queue_container.put(self.edge_services.services)
            else:
                logging.info("WHY did centre trigger self-migration?")
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_deploy(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        try:
            service_json = yaml.safe_load(msg)
            logging.info("request discovery a service {}".format(service_json))
            edge_service = self.start_edge_service(service_json)
            payload_json = get_json_from_object(edge_service)
            payload = '{}'.format(payload_json)
            topic = '{}/{}'.format(Constants.ALLOCATED,
                                   service_json[Constants.END_USER])
            self.publish(topic, payload)
            logging.info("Publish topic {}, payload: {}".format(topic,
                                                                payload))
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_destroy(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        try:
            service_json = yaml.safe_load(msg)
            logging.info("request destroy a service {}".format(service_json))
            removing_service = MigrateNode(**service_json)
            if self.edge_services.find_index_service(removing_service) is None:
                logging.exception("Cannot find removing service "
                                  "in this server.")
                return
            # Destroy the running container
            docker_client = docker.from_env()
            container_name = removing_service.service_name +\
                removing_service.end_user
            logging.info("check container name {}".format(container_name))
            try:
                container = docker_client.containers.get(container_name)
                if container.status == 'running':
                    logging.info("Detect the removing container {}"
                                 " is running.".format(container_name))
                    container.remove(force=True)
                self.unsubscribe_monitor_service(removing_service.end_user)
                self.edge_services.remove_service(removing_service)
            except docker.errors.NotFound:
                print("Not available docker container_name {}".
                      format(container_name))
            self.mon_queue_container.put(self.edge_services.services)
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_neighbor_off(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        server_name = topic.split('/')[2]
        server_info = self.my_neighbors.get_server_info(server_name)
        if server_info is not None:
            self.my_neighbors.remove_server(server_info)

    def process_updated_servers(self, client, userdata, message):
        global ready
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        try:
            all_servers = yaml.safe_load(msg)
            is_registered = self.my_neighbors.update_my_neighbors(
                self.server_info, all_servers)
            if not is_registered:
                self.register_to_centre()
            ready = True
            self.mon_queue_network.put(self.my_neighbors.get_ip_servers())
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_monitor_service(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("Process topic {}, payload: {}".format(topic, msg))
        try:
            # report = yaml.safe_load(msg)
            end_user = topic.split('/')[2]
            services = self.edge_services.get_services_from_user(end_user)
            for service in services:
                service.request += 1
                if service.request == 3:
                    logging.debug("Trigger pre-measure")
                    self.source_queue.put(('pre_measure',
                                          service.get_migrate_service()))
                elif service.request == 4:
                    logging.debug("Trigger measure")
                    self.source_queue.put(('measure',
                                          service.get_migrate_service()))
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def report_namedtuple(self, report, topic_prefix):
        topic = '{}/{}'.format(topic_prefix,
                               self.server_info['server_name'])
        payload = json.dumps(report.__dict__)
        logging.info('Publish to topic {}: {}'.format(topic, payload))
        self.publish(topic, payload)

    def network_report(self, report):
        self.report_namedtuple(report, Constants.MONITOR_EDGE)

    def server_report(self, report):
        self.report_namedtuple(report, Constants.MONITOR_SERVER)

    def container_report(self, report):
        self.report_namedtuple(report, Constants.MONITOR_CONTAINER)

    def source_dirty_rate_cb(self, **kwargs):
        delta_memory = kwargs['delta_memory']
        pre_checkpoint = kwargs['pre_checkpoint']
        time_checkpoint = kwargs['time_checkpoint']
        time_xdelta = kwargs['time_xdelta']
        logging.debug("Found dirty rate: {}, pre_checkpoint: {}".format(
            delta_memory, pre_checkpoint))
        # Update service
        service = self.edge_services.get_service(kwargs['end_user'],
                                                 kwargs['service_name'])
        service.delta_memory = delta_memory
        service.pre_checkpoint = pre_checkpoint
        service.time_checkpoint = time_checkpoint
        service.time_xdelta = time_xdelta
        logging.debug("Updated time_checkpoint {}, time_xdelta: {}".
                      format(time_checkpoint, time_xdelta))
        self.mon_queue_container.put(self.edge_services.services)

    def source_migrate_cb(self, **kwargs):
        service = MigrateNode(**kwargs)
        self.unsubscribe_monitor_service(service.end_user)
        logging.debug("Remove service: {}".format(service))
        self.edge_services.remove_service(service)
        self.mon_queue_container.put(self.edge_services.services)

    def source_prepare_cb(self, **kwargs):
        service = MigrateNode(**kwargs)
        topic = '{}/{}'.format(Constants.PRE_MIGRATED, service.end_user)
        payload = json.dumps(kwargs)
        logging.info('Publish to topic {}:{}'.format(topic, payload))
        self.publish(topic, payload)

    def source_report_cb(self, report):
        topic = '{}/{}/{}'.format(Constants.MIGRATE_REPORT, 'source',
                                  self.server_info['server_name'])
        method = report.method
        obj = {
            'source': self.server_info['server_name'],
            'dest': self.my_neighbors.get_server_name_from_ip(report.dest_ip),
            'service': report.service,
            'checkpoint': report.checkpoint,
            'rsync': report.rsync,
            'migrate': report.migrate,
            'premigration': report.premigration,
            'restore': report.restore,
        }
        if method != Constants.NON_LIVE_MIGRATION:
            obj['pre_checkpoint'] = report.pre_checkpoint
            obj['pre_rsync'] = report.pre_rsync
            obj['prepare'] = report.prepare
            obj['xdelta_source'] = report.xdelta_source
            obj['final_rsync'] = report.final_rsync
            obj['size_pre_rsync'] = report.size_pre_rsync
            obj['size_final_rsync'] = report.size_final_rsync
            obj['size_pre_rsync'] = report.size_pre_rsync
            obj['size_rsync'] = report.size_rsync
        payload = json.dumps(obj)
        logging.info("Publish to topic {}: {}".format(topic, payload))
        self.publish(topic, payload)

    def dest_migrate_cb(self, **kwargs):
        service = MigrateNode(**kwargs)
        topic = '{}/{}'.format(Constants.MIGRATED,
                               service.end_user)
        payload = json.dumps(kwargs)
        self.publish(topic, payload)
        logging.info("Publish topic: {}, payload: {}".format(topic, payload))
        self.edge_services.add_service(service)
        self.subscribe_monitor_service(service.end_user)
        self.mon_queue_container.put(self.edge_services.services)

    def dest_report_cb(self, report):
        topic = '{}/{}/{}'.format(Constants.MIGRATE_REPORT, 'dest',
                                  self.server_info['server_name'])
        method = report.method
        obj = {
            'source':
            self.my_neighbors.get_server_name_from_ip(report.source_ip),
            'dest': self.server_info['server_name'],
            'service': report.service,
            'restore': report.restore
        }
        if method != Constants.NON_LIVE_MIGRATION:
            obj['xdelta_dest'] = report.xdelta_dest
        payload = json.dumps(obj)
        logging.info("Publish to topic {}: {}".format(topic, payload))
        self.publish(topic, payload)


def my_exception_handler(exc_type, value, tb):
    logging.error("".join(traceback.format_exception(exc_type, value, tb)))
    logging.error("Uncaught: {} {}".format(value,
                                           traceback.format_exception(exc_type,
                                                                      value,
                                                                      tb)))
    sys.__excepthook__(exc_type, value, tb)
    sys.exit(1)


if __name__ == '__main__':
    out = check_output(['whoami'])
    if out != 'root\n':
        logging.error('You must run this script under root permission!')
        sys.exit(-1)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--verbose',
        help="Verbose print debug.",
        action='store_true')
    parser.add_argument(
        '--rsync',
        help="using rsync option instead of xdelta as default.",
        action='store_true')
    # Capacity (C_s) = 3500 Mhz
    # Size of container of Openface (S_Du) = 1860 MB
    # Size of checkpoint (S_CPu) = 186 MB
    # t_restore = 3.5
    # t_checkpoint = 0.28
    #
    # phi = C_s*t_checkpoint/S_Du
    # rho = C_s*t_restore/(S_Du+S_CPu)
    # TODO: deprecated
    parser.add_argument(
        '--rho',
        help="Rho parameter of the server",
        default=None)  # 5.987)
    parser.add_argument(
        '--phi',
        help="Phi parameter of the server",
        default=None)  # 0.527)
    parser.add_argument(
        '--distance',
        type=int,
        help="Distance to the core cloud. Default is 0 (service at the cloud)",
        default=2)
    parser.add_argument(
        '--broker_ip',
        type=str,
        help="Broker IP.",
        default="172.18.35.76")
    parser.add_argument(
        '--log',
        type=str,
        help="Log file",
        default="_edge_server.log")
    parser.add_argument(
        '--log_level',
        type=str,
        help="Log level: INFO (Default), DEBUG.",
        default="INFO")
    parser.add_argument(
        '--conf',
        type=str,
        help="YAML file",
        default="edge_nodes.yml")
    args = parser.parse_args()

    FORMAT = '%(asctime)-15s %(levelname)s %(filename)s %(lineno)s %(message)s'
    if args.log_level:
        LOG_LVL = logging.DEBUG
    else:
        LOG_LVL = logging.INFO

    hostname = get_hostname()
    filename = args.log
    if hostname not in args.log:
        filename = hostname + filename
    check_swap_file(filename)
    logging.basicConfig(level=LOG_LVL, format=FORMAT, filename=filename)

    if args.verbose:
        print("Output to stdout")
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logging.Formatter(FORMAT))
        consoleHandler.setLevel(LOG_LVL)
        logging.getLogger('').addHandler(consoleHandler)

    # handle all uncaught exception
    # https://stackoverflow.com/questions/8050775/using-pythons-logging-module-to-log-all-exceptions-and-errors
    sys.excepthook = my_exception_handler
    cmd = ["git", "rev-parse", "--short", "HEAD"]
    version = check_output(cmd)
    logging.info("Start edge controller version {}".format(version))
    configs = DiscoveryYaml(args.conf)
    server_info_ = configs.get_server_info_from_name(hostname)
    rho = server_info_.get('rho')
    phi = server_info_.get('phi')
    bs_name = get_ap_ssid()
    logging.info("BS name: {}".format(bs_name))
    bs_x = configs.get_ap_info(bs_name, 'x')
    bs_y = configs.get_ap_info(bs_name, 'y')
    logging.info("BS location: ({},{})".format(bs_x, bs_y))
    server = ControllerServer(args.broker_ip, Constants.BROKER_PORT,
                              distance=args.distance,
                              rho=rho, phi=phi, bs_name=bs_name,
                              bs_x=bs_x, bs_y=bs_y)
    server.register_to_centre()

    # Start destination migration service
    dest_migration_thread = Thread(target=dest_migration_handler,
                                   args=[args.verbose,
                                         server])
    dest_migration_thread.setDaemon(True)
    dest_migration_thread.start()
    source_migration_thread = Thread(target=source_migration_handler,
                                     args=[args.verbose,
                                           server,
                                           server.source_queue])
    source_migration_thread.setDaemon(True)
    source_migration_thread.start()
    # Start network monitor service
    network_monitor_thread = Thread(target=network_monitor_handler,
                                    args=[server.network_report,
                                          server.mon_queue_network,
                                          args.broker_ip,
                                          args.conf])
    server_monitor_thread = Thread(target=server_monitor_handler,
                                   args=[server.server_report, args.conf])
    container_monitor_thread = Thread(target=container_monitor_handler,
                                      args=[server.container_report,
                                            server.mon_queue_container])
    network_monitor_thread.setDaemon(True)
    server_monitor_thread.setDaemon(True)
    container_monitor_thread.setDaemon(True)
    network_monitor_thread.start()
    server_monitor_thread.start()
    container_monitor_thread.start()
    server.loop_forever(retry_first_connection=True)
