from __future__ import division

import os
import sys
import time
import json
import math
import socket
import logging
import argparse
import threading
import traceback
import collections
from struct import pack
from subprocess import check_output
import yaml

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import Constants
import discovery_edge

import placement
from migrate_node import MigrateNode
from mqtt_protocol import MqttClient
from utilities import check_swap_file, get_default_interface
from communication_models import log_rssi_model_real as log_rssi_model
from communication_models import handover_constant
from communication_models import datarate_model
from estimator import euclidean_distance
import simulated_mobile_eu_db as db
import route
import datarate

from mobility_models import SimpleRoundTripMoving, CircleTripMoving

timeout = 40

def try_connect_with_timeout(sock, addr, timeout, debug=logging):
    start = time.time()
    err = 0
    while (time.time() - start) < timeout:
        err = sock.connect_ex(addr)
        if err == 0:
            break
        time.sleep(1)
    if err:
        raise socket.error
    debug.debug('Connect after {}s'.format(int(time.time() - start)))

BTSInfo = collections.namedtuple('BTSInfo', ['name', 'bssid', 'passwd', 'server',
                                             'x', 'y', 'ip'])

class Environment(object):
    def __init__(self, interface, rssi_model=log_rssi_model,
                 handover=handover_constant):
        self.bts = []
        self.eu = []
        self.rssi_model = rssi_model
        self.handover_model = handover
        self.interface = interface
        self.is_stop = False
        self.is_error = None
        self.route_man = None
        self.speed_man = None

    def place_bts(self, bts):
        self.bts.append(bts)

    def place_eu(self, eu):
        eu.env = self
        self.eu.append(eu)

    def get_rssi_list(self, x, y):
        ret = []
        for bts in self.bts:
            d = math.sqrt((x-bts.x)**2 + (y-bts.y)**2)
            rssi = self.rssi_model(d)
            ret.append({
                'SSID': bts.name,
                'BSSID': bts.bssid,
                'level': rssi
            })
        return ret

    def get_bts_info(self, name):
        return next((b for b in self.bts if b.name == name), None)

    def handover(self, eu, ssid, bssid):
        bts = next((i for i in self.bts if i.name == ssid), None)
        if bts is None:
            return None
        handover_time = self.handover_model(self, bts, eu)
        return handover_time

    def run_env(self, stop_time):
        """Start simulated environment
        """
        logging.info("Start simulator, time={}s".format(stop_time))
        start = time.time()
        self.route_man = route.RouteManager([u.end_user
                                             for u in self.eu])
        self.rate_man = datarate.SpeedManager(self.route_man,
                                              self.interface,
                                              dry_run=False)
        self.route_man.allocate_tables()
        # Note that this function must be called after
        # `allocate_tables`
        self.rate_man.allocate_speeds()
        for eu in self.eu:
            eu.run(stop_time)
        logging.info("Start wait loop")
        elapse_time = (time.time() - start)
        while (elapse_time < stop_time):
            if self.is_stop:
                break
            if self.is_error is not None:
                self.stop(self.is_error)
                break
            time.sleep(0.1)
            for eu in self.eu:
                eu.update_eu()
            elapse_time = time.time() - start
        logging.info("Stopping simulator")
        self.stop()

    def stop(self, error=None):
        """Stop the simulation.
        """
        self.is_stop = True
        for eu in self.eu:
            eu.terminate()
        self.route_man.release_tables()
        self.rate_man.clear_all()
        if error is not None:
            sys.exit(error) # Raise error and quit

class MobileDevice(object):
    def __init__(self, moving, **kwargs):
        self.end_user = kwargs.get('end_user', 'end_user')
        self.ssid = kwargs.get('ap_ssid', '')
        self.bssid = kwargs.get('ap_bssid', '')
        self.log = logging.getLogger(self.end_user)
        self.app = None
        self.env = None
        self.moving = moving
        self.is_connected = True
        self.reconnect_time = 0

    def update_eu(self, event=None):
        current = time.time()
        # Update position
        x, y = self.moving.get_new_position()
        # Update connect status
        if not self.is_connected and self.reconnect_time != 0:
            if self.reconnect_time < current:
                self.handover_cb()
                self.reconnect_time = 0
                # Route to a new server
                bts = self.env.get_bts_info(self.ssid)
                self.env.route_man.set_gw_ip(self.end_user, bts.ip)
        if self.is_connected:
            # Control speed
            self.device_update_rate()

    def device_update_rate(self):
        x, y = self.moving.get_new_position()
        levels = self.env.get_rssi_list(x, y)
        # Searching for the correct BS
        rssi = next((l['level'] for l in levels
                     if l['SSID'] == self.ssid), None)
        if rssi is None:
            # Something wrong happened
            self.log.error("Cannot find the rssi number for current"
                           " BS ({})".format(self.ssid))
        else:
            # Set the new limit
            new_speed = datarate_model(rssi)
            ret = self.env.rate_man.set_speed(self.end_user,
                                              new_speed)
            if ret == 0:
                self.log.info("Set the speed to {}".format(new_speed))



    def change_service_cb(self, new_ip, new_port):
        self.env.route_man.set_filter(self.end_user, new_ip, new_port)

    def terminate(self):
        self.log.info("{} is terminated".format(self.end_user))
        self.app.stop()

    def scan_rssi(self):
        if self.env is None:
            raise RuntimeError("Cannot found environment")
        x, y = self.moving.get_new_position()
        levels = self.env.get_rssi_list(x, y)
        ret = []
        self.log.debug('User position: {}, {}'.format(x, y))
        for l in levels:
            level = l['level']
            self.log.debug('RSSI to {}: {}'.format(l['SSID'], level))
            if level > -110:
                ret.append(l)
        return ret

    def handover_cb(self):
        self.is_connected = True
        self.user_cb()

    def connect_to_bts(self, name, bssid, cb):
        if self.env is None:
            raise RuntimeError("Cannot found environment")
        ret = self.env.handover(self, name, bssid)
        if ret is None:
            self.log.error('Cannot find bssid')
            return
        self.reconnect_time = time.time() + ret
        self.ssid = name
        self.bssid = bssid
        self.user_cb = cb
        self.is_connected = False

    def get_current_bts(self):
        return self.ssid, self.bssid

    def notify_error(self):
        self.env.is_error = 1

    def run(self, stop_time):
        bts = self.env.get_bts_info(self.ssid)
        self.env.route_man.set_gw_ip(self.end_user, bts.ip)
        self.moving.start_moving()
        self.app.run()

EU_STATE = type('Enum', (), {'INIT': 1, 'NORMAL': 2, 'MIGRATION': 3,
                             'HANDOVER': 4, 'TERMINATED':5})

class MobileEUTestApp(MqttClient):
    def __init__(self, **kwargs):
        super(MobileEUTestApp, self).__init__(**kwargs)
        self.test_img = kwargs.get('test_img',
            os.path.join(os.path.dirname(__file__),
                         'ObamaLeeHsienLoong.jpg'))
                        #'ObamaSylvesterStallone.jpg'))
        self.end_user = kwargs.get('end_user', 'end_user')
        self.service_name = kwargs.get('service_name', Constants.YOLO)
        self.log = kwargs.get('log', logging.getLogger(self.end_user))
        self.device = kwargs.get('device', None)
        self.max_fail = kwargs.get('max_fail', 20)
        self.database_name = kwargs.get('database',
                                    'eu_{}_{}.db'.format(self.end_user,
                                                    self.service_name))
        check_swap_file(self.database_name, '-nl')
        self.database = db.DBeu(database=self.database_name)
        self.log.info("Create new database at: {}".format(self.database_name))
        self.state = EU_STATE.INIT
        self.service = None
        self.data = None
        # Register callbacks
        self.allocated_topic='{}/{}'.format(Constants.ALLOCATED, self.end_user)
        self.migrated_topic='{}/{}'.format(Constants.MIGRATED, self.end_user)
        self.handover_topic='{}/{}'.format(Constants.HANDOVER, self.end_user)
        self.message_callback_add(self.allocated_topic, self.process_allocated)
        self.message_callback_add(self.migrated_topic, self.process_migrated)
        self.message_callback_add(self.handover_topic, self.process_handover)
        current_bts = self.device.get_current_bts()
        self.log.info(
            "\n***start simulate service:{}, name:{}, AP:{}@{}, broker:{}***\n".\
            format(self.service_name, self.end_user, current_bts[0],
                   current_bts[1], self.broker_ip))
        self.connect_timeout = 5
        self.stream_sock = None
        self.consecutive_fail = 0

    def on_connect(self, client, userdata, flag, rc):
        self.log.info("Connected to broker with result code {}".format(rc))
        self.subscribe([(self.allocated_topic, 1),
                        (self.migrated_topic, 1),
                        (self.handover_topic, 1)])

    def try_connect_to_service(self, timeout):
        if self.service is None:
            self.log.error("Request service before discover it")
            return None
        self.log.info("try to connect {}:{} with timeout {}".
                      format(self.service.ip, self.service.port, timeout))
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if timeout is None:
                sock.connect(
                    (self.service.ip, int(self.service.port)))
            else:
                try_connect_with_timeout(
                    sock, (self.service.ip, int(self.service.port)),
                    timeout, debug=self.log)
            return sock
        except socket.error:
            self.log.error('Cannot open a socket to edge service {}:{}.'.
                           format(self.service.ip, self.service.port))
            return None

    def send_data(self, sock, timeout=4.0):
        if self.data is None:
            with open(self.test_img, 'rb') as f:
                self.data = f.read()
        sent_size = len(self.data)
        length = pack('!i', sent_size)
        # sendall to make sure it blocks if there's back-pressure on the socket
        if sock is None:
            self.log.warn("Socket is None")
            return 0
        sock.settimeout(timeout)
        try:
            sock.sendall(length + self.data)
            return sent_size
        except socket.error as e:
            self.log.error("Failed to send, socket {}".format(e))
            return 0

    def recv_data(self, sock, timeout=5.0):
        if sock is None:
            self.log.warn("socket is None")
            return ''
        sock.settimeout(timeout)
        try:
            return sock.recv(1024)
        except socket.error as e:
            self.log.error("Failed to receive data from socket {}".format(e))
            return ''

    def query_service(self, connect_timeout):
        start_request = time.time()
        if self.stream_sock is None:
            self.log.error("Cannot connect to server, try again")
            self.stream_sock = self.try_connect_to_service(self.connect_timeout)
            return 1
        size = self.send_data(self.stream_sock)
        if self.stream_sock is not None:
            self.stream_sock.settimeout(None)
        if size == 0:
            self.log.error("Cannot send to service, try again")
            self.stream_sock = self.try_connect_to_service(self.connect_timeout)
            return 2
        received = self.recv_data(self.stream_sock)
        if self.stream_sock is not None:
            try:
                # NOTE: This line raise: "[Errno 9] Bad file
                # descriptor" but I don't know why. The socker may be
                # closed.
                self.stream_sock.settimeout(None)
            except socket.error:
                self.log.error("Unexpected error with socket")
                self.stream_sock = None
        if received == '':
            self.log.error("Service is terminated, try again!")
            if self.stream_sock is not None:
                self.stream_sock = self.try_connect_to_service(self.connect_timeout)
            return 3
        self.log.debug('Received: {}'.format(received))
        end = time.time()
        proc_time = self.parse_process_time(received)
        self.report_service(start_request*10**9, end*10**9, size,
                            proc_time)
        current_bts = self.device.get_current_bts()
        self.database.update_service(timestamp=start_request*10**6,
                                     user_id=self.end_user,
                                     service_id=self.service.get_container_name(),
                                     ssid = current_bts[0],
                                     bssid = current_bts[1],
                                     server_name = self.service.server_name,
                                     proc_delay = proc_time,
                                     e2e_delay = (end-start_request)*1000,
                                     request_size=size)
        # sock.close()
        return 0

    def report_service(self, start, end, size, proc_time):
        """Reports request information to the centralized server

        Example::

            {'startTime[ns]':3799849462390626,
            'endTime[ns]':3799849817351511,
            'processTime[ms]':301.27978515625,
            'sentSize[B]':5765,
            'end_user':'Userd8e999d3c22e8f60',
            'service_name':'openface',
            'ssid':'edge01',
            'bssid':'52:3e:aa:49:98:cb'}

        """
        report = {Constants.END_USER: self.end_user,
                  Constants.SERVICE_NAME: self.service_name}
        report["startTime[ns]"]=start
        report["endTime[ns]"]=end
        report["sentSize[B]"]=size
        report["processTime[ms]"]=proc_time
        current_bts = self.device.get_current_bts()
        report[Constants.ASSOCIATED_SSID] = current_bts[0]
        report[Constants.ASSOCIATED_BSSID] = current_bts[1]
        topic = '{}/{}'.format(Constants.MONITOR_SERVICE, self.end_user)
        payload = json.dumps(report)
        self.log.debug("Publish topic {}, payload {}".format(topic, payload))
        self.publish(topic, payload)

    def report_rssi(self, nearby_aps):
        """

        Example::

            {'end_user':'xxx',
            'service_name':'yolo',
            'nearbyAP':[
                {'SSID':'edge01',
                 'BSSID':'02:03:04:05:06:07',
                 'level':-58
                 },...
             ]}

        """
        report = {Constants.END_USER: self.end_user,
                  Constants.SERVICE_NAME: self.service_name}
        report[Constants.NEARBY_AP] = nearby_aps
        topic = '{}/{}'.format(Constants.MONITOR_EU, self.end_user)
        payload = json.dumps(report)
        self.log.debug("Publish topic {}, payload {}".format(topic, payload))
        self.publish(topic, payload)

    def discovery_service(self):
        self.log.info("begin discover service {} for user {} to broker {}".
                      format(self.service_name, self.end_user, self.broker_ip))
        current_bts = self.device.get_current_bts()
        discovery_service = {
            Constants.SERVICE_NAME: self.service_name,
            Constants.END_USER: self.end_user,
            Constants.ASSOCIATED_SSID: current_bts[0],
            Constants.ASSOCIATED_BSSID: current_bts[1]}
        payload = json.dumps(discovery_service)
        self.publish(Constants.DISCOVER, payload)

    def parse_process_time(self, recv):
        try:
            msg_json = yaml.safe_load(recv)
            general = msg_json['general']
            proc_time = general['processTime[ms]']
            return proc_time
        except KeyError:
            self.log.error("Invalid key")
            self.log.error(traceback.format_exc())
        except yaml.YAMLError:
            self.log.error("Error parsing YAML msg {}".format(recv))
        return None

    def report_rssi_thread(self):
        while self.state != EU_STATE.TERMINATED:
            time.sleep(2)
            if self.device.is_connected:
                nearby_aps = self.device.scan_rssi()
            self.report_rssi(nearby_aps)
        self.log.info("Stop rssi report thread")

    def stream_request_thread(self, discovery_timeout=30, connect_timeout=5):
        start = time.time()
        start_discovery = time.time()
        cnt = 0
        if self.manual:
            self.service = MigrateNode()
            self.service.service_name = 'openface'
            self.service.ip = '172.18.35.76'
            self.service.port = 9912
            self.log.info("!!!Manual service  {} to server {}:{}".\
                          format(self.service.service_name,
                                 self.service.ip,
                                 self.service.port))
            self.stream_sock = self.try_connect_to_service(self.connect_timeout)
            self.state = EU_STATE.NORMAL
        else:
            self.log.info("Start discovery service")
            self.discovery_service()
        while self.state != EU_STATE.TERMINATED:
            if not self.device.is_connected:
                time.sleep(0.1)
                continue
            if self.state == EU_STATE.INIT:
                current = time.time()
                if (current - start_discovery) > discovery_timeout:
                    self.log.error("Discovery timeout, try to discovery again")
                    self.discovery_service()
                    start_discovery = time.time()
            elif self.state == EU_STATE.MIGRATION:
                # Do nothing
                pass
            else:
                # Try to request
                cnt += 1
                if cnt % 100 == 0:
                    self.log.info('Try to request: {}'.format(cnt))
                elif cnt % 50 == 0:
                    self.log.debug('Try to request: {}'.format(cnt))
                ret = self.query_service(connect_timeout)
                if ret != 0:
                    self.consecutive_fail += 1
                    logging.warn("Error count: {}".format(self.consecutive_fail))
                    if self.consecutive_fail >= self.max_fail:
                        self.device.notify_error()
                else:
                    self.consecutive_fail = 0
            time.sleep(0)
        if self.stream_sock is not None:
            self.stream_sock.close()
        self.log.info("Stop stream request thread")

    def run(self):
        if self.manual:
            self.stream_thread = threading.Thread(target=self.stream_request_thread,
                                              args=[])
        else:
            self.rssi_thread = threading.Thread(target=self.report_rssi_thread,
                                                args=[])
            self.stream_thread = threading.Thread(target=self.stream_request_thread,
                                                  args=[])
            self.rssi_thread.setDaemon(True)
            self.rssi_thread.start()
            self.loop_start()
        self.stream_thread.setDaemon(True)
        self.stream_thread.start()

    def stop(self):
        self.state = EU_STATE.TERMINATED
        self.report_leaving()
        self.rssi_thread.join()
        self.stream_thread.join()
        self.loop_stop(force=True)
        total = self.database.get_user_request_summary()
        self.log.info("User {} made {} requests".format(self.end_user,
                                                        total))
        self.database.close()
        self.log.info("Client stopped!")

    def report_leaving(self):
        topic = '{}/{}'.format(Constants.LWT_EU, self.end_user)
        payload = 'exit'
        self.log.info("Publish topic {}, payload {}".format(topic, payload))
        self.publish(topic, payload)
        self.disconnect()

    def handover_cb(self):
        current_bts = self.device.get_current_bts()
        topic = '{}/{}'.format(Constants.HANDOVERED, self.end_user)
        payload = json.dumps({
            Constants.ASSOCIATED_SSID: current_bts[0],
            Constants.ASSOCIATED_BSSID: current_bts[1]
        })
        self.log.info("Publish topic {}, payload {}".format(topic, payload))
        self.publish(topic, payload)

    # MQTT Handlers ----------------------------------------------------------
    def process_handover(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        self.log.info("process topic {}, payload: {}".format(topic, msg))
        try:
            msg_json = yaml.safe_load(msg)
            ssid = msg_json[Constants.NEXT_SSID]
            bssid = msg_json[Constants.NEXT_BSSID]
            self.database.add_event(self.end_user, 'handover', msg)
            self.device.connect_to_bts(ssid, bssid, self.handover_cb)
            self.log.info("*****Handover to AP {}@{}".format(ssid, bssid))
            if self.stream_sock is not None:
                self.log.info("Close old socket")
                self.stream_sock.shutdown(socket.SHUT_RDWR)
                self.stream_sock.close() # Close old socket to start a new one
                self.stream_sock = None
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_allocated(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        self.log.debug("process topic {}, payload: {}".format(topic, msg))
        try:
            msg_json = yaml.safe_load(msg)
            self.service = MigrateNode(**msg_json)
            self.database.add_event(self.end_user, 'allocated', msg)
            self.device.change_service_cb(self.service.ip, self.service.port)
            self.log.info("!!!Got a discovered service {} to server {}:{}".\
                          format(self.service.service_name,
                                 self.service.ip,
                                 self.service.port))
            self.stream_sock = self.try_connect_to_service(self.connect_timeout)
            if self.state != EU_STATE.TERMINATED:
                self.state = EU_STATE.NORMAL
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_migrated(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        self.log.debug("process topic {}, payload: {}".format(topic, msg))
        try:
            service_json = yaml.safe_load(msg)
            self.service = MigrateNode(**service_json)
            if self.state != EU_STATE.TERMINATED:
                self.state = EU_STATE.NORMAL
            self.device.change_service_cb(self.service.ip, self.service.port)
            self.database.add_event(self.end_user, 'migrated', msg)
            if self.stream_sock is not None:
                self.log.info("Close old socket")
                self.stream_sock.shutdown(socket.SHUT_RDWR)
                self.stream_sock.close() # Close old socket to start a new one
                self.stream_sock = None
            self.log.info("*****Migrated to Server {} {}:{}".\
                          format(self.service.server_name, self.service.ip,
                          self.service.port))
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

def run_simulation(conf_file, conf_eu_file, interface, log_file,
                   log_level=logging.INFO,
                   log_level_file=logging.DEBUG, sim_time=100,
                   manual=False):
    env = Environment(interface)
    if os.path.isfile(log_file):
        check_output(['savelog', '-ntl', log_file])
    FMT='%(asctime)-15s %(name)s %(levelname)s %(filename)s %(lineno)s %(message)s'
    logging.basicConfig(level=log_level_file,
                        format=FMT,
                        datefmt='%Y-%m-%d %H:%M:%S',
                        filename=log_file,
                        filemode='w')
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(logging.Formatter(FMT))
    logging.getLogger('').addHandler(console)
    configs = discovery_edge.DiscoveryYaml(conf_file)
    config_eus = discovery_edge.DiscoveryYaml(conf_eu_file)
    broker_ip = configs.get_centre_ip()
    (place_model, number_bs, distance_bs) = configs.get_placement_bs_model()
    # Base-station placement
    coords = None
    if place_model == 'circle':
        bs_locations = placement.CirclePlacement(number_bs = number_bs,
            distance_bs = distance_bs)
        coords = bs_locations.get_position_bs()
    elif place_model == 'line':
        bs_locations = placement.LinearPlacement(number_bs = number_bs,
            distance_bs = distance_bs)
        coords = bs_locations.get_position_bs()
    # Place base-station
    for i in range(number_bs):
        ap = configs.aps[i]
        ip = configs.get_server_ip(ap['server'])
        ap['ip'] = ip
        if coords is not None: # overwrite the manual locations
            ap['x'] = coords[i][0]
            ap['y'] = coords[i][1]
        bts = BTSInfo(**ap)
        env.place_bts(bts)

    # place end-user
    for user in config_eus.get_end_users():
        end_user = user['name']
        service_name = user.get('service', Constants.OPENFACE)
        # Find start AP
        start_ap = min(configs.aps, key=lambda ap: ap['x'])
        stop_ap = max(configs.aps, key=lambda ap: ap['x'])
        # Create moving model
        moving_conf = user.get('moving', None)
        if moving_conf is None:
            # The default moving model
            moving = SimpleRoundTripMoving(velocity=1, # 1m/s
                                           wait_time=30,
                                           start_x=start_ap['x'],
                                           stop_x=stop_ap['x'])
        else:
            velocity = moving_conf.get('velocity', 1)
            moving_type = moving_conf.get('type', 'simple_roundtrip')
            if moving_type == 'simple_roundtrip':
                start_point = moving_conf.get('start_point', start_ap['x'])
                stop_point = moving_conf.get('stop_point', stop_ap['x'])
                y = moving_conf.get('y', 0)
                wait_time = moving_conf.get('wait_time', 30)
                moving = SimpleRoundTripMoving(velocity=velocity,
                                               wait_time=wait_time,
                                               start_x=start_point,
                                               stop_x=stop_point,
                                               y=y)
            elif moving_type == 'circle_trip':
                start_x = moving_conf.get('start_x', start_ap['x'])
                start_y = moving_conf.get('start_y', start_ap['y'])
                wait_time = moving_conf.get('wait_time', 30)
                direction = moving_conf.get('direction', 1) #anti-clockwise
                radius = moving_conf.get('radius', 10)
                moving = CircleTripMoving(velocity = velocity,
                                          wait_time = wait_time,
                                          start_x = start_x,
                                          start_y = start_y,
                                          direction = direction,
                                          radius = radius)
            else:
                user.log.error("Invalid moving type, ignore this user")
                continue
        # Create simulated mobile device
        # TODO: Improve this config.
        user_x = moving_conf.get('start_point', 0)
        user_y = moving_conf.get('y', 0)
        nearest_ap = min(configs.aps,
                         key=lambda ap: euclidean_distance((user_x, user_y),
                                                           (ap['x'], ap['y'])))
        logging.info('Adding user {}'.format(end_user))
        logging.info('The nearest AP for user is {}'.\
                     format(nearest_ap['name']))
        device = MobileDevice(moving, end_user=end_user,
                              ap_ssid=nearest_ap['name'],
                              ap_bssid=nearest_ap['bssid'])
        mobile_app = MobileEUTestApp(device=device, end_user=end_user,
                                     service_name=service_name,
                                     broker_ip=broker_ip,
                                     broker_port=9999)
        mobile_app.manual = manual
        device.app = mobile_app
        env.place_eu(device)
    try:
        env.run_env(sim_time)
    except KeyboardInterrupt:
        env.stop()
    except Exception:
        logging.error(traceback.format_exc())
        env.stop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--service',
        type=str,
        help='Service name is either: openface, yolo, simple',
        default='yolo')
    parser.add_argument(
        '--save',
        type=str,
        help='Save log file',
        default='e2e_delay.log')
    parser.add_argument(
        '--conf',
        type=str,
        help='Config file for BSs and servers',
        default='edge_nodes.yml')
    parser.add_argument(
        '--conf_eu',
        type=str,
        help='Config file for end-users',
        default='eu_simple.yml')
    parser.add_argument(
        '--noq',
        type=int,
        help='Number of queries',
        default=100)
    parser.add_argument(
        '--migration',
        help='If called, EU report rssi, and service info.',
        action='store_true')
    parser.add_argument(
        '--level',
        help='Log level',
        default='INFO')
    parser.add_argument(
        '--level_file',
        help='Log level file',
        default='DEBUG')
    parser.add_argument(
        '--time',
        help='Simulation time',
        type=int,
        default=100)
    parser.add_argument(
        '--manual',
        action='store_true')
    parser.add_argument(
        '--interface',
        help='Network interface',
        default='')
    args = parser.parse_args()
    if args.interface == '':
        args.interface = get_default_interface()
    run_simulation(args.conf,
                   args.conf_eu,
                   args.interface,
                   args.save,
                   log_level=getattr(logging, args.level),
                   log_level_file=getattr(logging, args.level_file),
                   sim_time=args.time,
                   manual=args.manual)
