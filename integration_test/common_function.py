import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import json
import yaml
import time
import socket
import logging
from struct import pack

import pytest

import Constants
from Constants import *
from mqtt_protocol import MqttClient

OPENFACE = 'openface'
YOLO = 'yolo'
SIMPLE_SERVICE = 'simple'

debug = True
timeout = 150

def try_connect_with_timeout(sock, addr, timeout, debug=False):
    start = time.time()
    err = 0
    while (time.time() - start) < timeout:
        err = sock.connect_ex(addr)
        if err == 0:
            break
        time.sleep(1)
    if err:
        raise socket.error
    if debug:
        print('Connect after {}s'.format(int(time.time() - start)))

class DiscoveryMqttClient(MqttClient):
    def __init__(self, **kwargs):
        super(DiscoveryMqttClient, self).__init__(**kwargs)
        self.test_result = False
        self.discovered_service = None

    def process_result(self, clien, userdata, message):
        result = message.payload
        #print("result = {}".format(result))
        if result != None:
            self.discovered_service = yaml.safe_load(result)
            self.test_result = True
            print("!!! Discovered a service {}".format(self.discovered_service))
        else:
            print("FAILED to discover service {} at AP {} for user {}".
                format(service_name, ap_ssid, end_user))
            self.test_result = False
            pytest.fail('No return message from edge services.')

    def publish(self, topic, payload):
        super(DiscoveryMqttClient, self).publish(topic, payload, qos=1)

def mqtt_discovery_service(server_ip, ap_ssid, ap_bssid, end_user, service_name, timeout=30):
    print("begin discover and associate service {} for user {} to broker {}".
           format(service_name, end_user, server_ip))
    discovery_service = {
        SERVICE_NAME: service_name,
        END_USER: end_user,
        ASSOCIATED_SSID: ap_ssid,
        ASSOCIATED_BSSID: ap_bssid}
    payload = json.dumps(discovery_service)
    mqttClient = DiscoveryMqttClient(
        client_id='testMqtt',
        clean_session=True,
        broker_ip=server_ip,
        broker_port=BROKER_PORT,
        keepalive=60)
    cb_topic = '{}/{}'.format(ALLOCATED, end_user)
    mqttClient.message_callback_add(cb_topic, mqttClient.process_result)
    mqttClient.subscribe((cb_topic, 1))
    mqttClient.loop_start()
    time.sleep(1)
    mqttClient.publish(DISCOVER, payload)
    start = time.time()
    while mqttClient.test_result is False and (time.time() - start) < timeout:
        time.sleep(0.001)
    print("Got result after {}s".format(time.time() - start))
    mqttClient.disconnect()
    time.sleep(0.5)
    return mqttClient.test_result, mqttClient.discovered_service

def query_simple(service_ip, service_port, dirty_rate=0):
    service_port = int(service_port)
    print("query simple to {}:{} with dirty_rate {}".
        format(service_ip, service_port, dirty_rate))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try_connect_with_timeout(sock, (service_ip, service_port), 120, debug=True)
        sock.send("{}\n".format(dirty_rate)) # Dirty memory 1Mb/s
        sock.close()
    except socket.error:
        pytest.fail('Cannot open a socket to edge service {}:{}'.
                format(service_ip, service_port))

def query_service(source_ap, source_bssid, end_user, service_name, service_ip,
                  service_port, timeout, debug = False):
    print("begin query service to {} at port {}".
            format(service_ip, service_port))
    service_port = int(service_port)
    imgdir = 'integration_test/testImage.jpg'
    mqttClient = MqttMigrationTrigger(
        client_id='testMqttQuery',
        clean_session=True,
        broker_ip='10.0.99.2',
        broker_port='9999',
        keepalive=60,
        lwt_topic='{}/{}'.format(LWT_EU, end_user))
    mqttClient.loop_start()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if timeout is None:
            sock.connect((service_ip, service_port))
        else:
            try_connect_with_timeout(sock, (service_ip, service_port), timeout,
                                     debug=True)
        with open(imgdir, 'rb') as f:
            data = f.read()
            f.close()
            start = time.time()
            # Use struct to make sure we have a consistent endiannes on the length
            length = pack('!i', len(data))
            # sendall to make sure it blocks if there's back-pressure on the socket
            sock.sendall(length)
            sock.sendall(data)
            print("Sent data: {} [B] time: {} [s]".format(len(data), time.time() - start))
            # Receive data from the server and shut down
            received = sock.recv(1024)
            sock.close()
            print("Received: {}, length {}".format(received, len(received)))
            end = time.time()
            last_elapsed_time = end - start
            print("Total elapsed time: {} [s]".format(last_elapsed_time))
            if received != '':
                try:
                    msg_json = yaml.safe_load(received)
                    general_json = msg_json['general']
                    proc_time = general_json['processTime[ms]']
                except yaml.YAMLError, KeyError:
                    print("Error parsing YAML msg {}".format(received))
                    pytest.fail("Unexpected message")
                assert True
                report = {
                    Constants.END_USER: end_user,
                    Constants.SERVICE_NAME: service_name,
                    Constants.ASSOCIATED_SSID: source_ap,
                    Constants.ASSOCIATED_BSSID: source_bssid,
                    "startTime[ns]": start*(10.0**9),
                    "endTime[ns]": end*(10.0**9),
                    "sentSize[B]": len(data),
                    "processTime[ms]" : proc_time
                }
                topic = '{}/{}'.format(Constants.MONITOR_SERVICE, end_user)
                payload = json.dumps(report)
                mqttClient.publish(topic, payload)
                print("Publish topic {}, payload {}".format(topic, payload))
            else:
                pytest.fail("None return message for this request.")
    except socket.error:
        pytest.fail('Cannot open a socket to edge service {}:{}'.
                format(service_ip, service_port))
    mqttClient.disconnect()

class MqttMigrationTrigger(MqttClient):
    def __init__(self, **kwargs):
        super(MqttMigrationTrigger, self).__init__(**kwargs)
        self.discovery_result = False
        self.migrated_result = False

    def process_migrated(self, clien, userdata, message):
        result = message.payload
        logging.info("Migrated info: ".format(result))
        if result != None:
            migrated_info = yaml.safe_load(result)
            migrated_service_json = migrated_info[SERVICE]
            self.migrated_service = yaml.safe_load(migrated_service_json)
            self.migrated_result = True
            print("!!! Migreated a service {}".format(self.migrated_service))
        else:
            self.migrated_result = False
            pytest.fail('FAILED to migrate service.')

def mqtt_report_monitor_rssi_info(broker_ip, ap_ssid, ap_bssid, dest_ap,
    end_user, service_name):
    print("Trigger migration from {} to {}".format(ap_ssid, dest_ap))
    timeout = 60
    monitor_msg_from_eu = {
        END_USER: end_user,
        SERVICE_NAME: service_name,
        'nearbyAP': [
            {'SSID': ap_ssid,
             'BSSID': ap_bssid,
             'level': -82},
            {'SSID': dest_ap,
             'BSSID': '86:16:f9:0f:b5:ce',
             'level': -58},
        ] }
    mqttClient = MqttMigrationTrigger(
        client_id='testMqttMigration',
        clean_session=True,
        broker_ip=broker_ip,
        broker_port=BROKER_PORT,
        keepalive=60,
        lwt_topic='{}/{}'.format(LWT_EU, end_user))
    migrated_topic = '{}/{}'.format(MIGRATED, end_user)
    mqttClient.message_callback_add(migrated_topic, mqttClient.process_migrated)
    mqttClient.subscribe([(migrated_topic, 1)])
    mqttClient.loop_start()
    time.sleep(1)
    payload = '{}'.format(monitor_msg_from_eu)
    start = time.time()
    topic = '{}/{}'.format(MONITOR_EU, end_user)
    mqttClient.publish(topic, payload)
    print("!!!Publish topic {} payload {}".format(topic, payload))
    while mqttClient.migrated_result is False and (time.time() - start) < timeout:
        time.sleep(0.001)
    print("Total time from trigger migration to return msg: {}".format(
        time.time() - start))
    assert mqttClient.migrated_result == True
    service_ip = mqttClient.migrated_service['ip']
    service_port = int(mqttClient.migrated_service['port'])
    mqttClient.disconnect()
    return service_ip, service_port

def leaving_notification(broker_ip, end_user):
    topic = '{}/{}'.format(LWT_EU, end_user)
    payload = 'exit'
    mqttClient = MqttClient(
        client_id='testMqttMigration',
        clean_session=True,
        broker_ip=broker_ip,
        broker_port=BROKER_PORT)
    print("publish topic {}, payload {}".format(topic, payload))
    mqttClient.publish(topic, payload)

def mqtt_report_monitor_service(broker_ip, my_ssid, my_bssid, end_user, service_name):
    monitor_msg_from_eu = {
        Constants.END_USER: end_user,
        Constants.SERVICE_NAME: service_name,
        Constants.ASSOCIATED_SSID: my_ssid,
        Constants.ASSOCIATED_BSSID: my_bssid,
        'startTime[ns]':3685421149965579,
        'endTime[ns]':3685422655153495,
        'processTime[ms]':301.27978515625,
        'sentSize[B]':5765}
    topic = '{}/{}'.format(Constants.MONITOR_SERVICE, end_user)
    mqttClient = MqttMigrationTrigger(
        client_id='testMqttMigration',
        clean_session=True,
        broker_ip=broker_ip,
        broker_port=BROKER_PORT,
        keepalive=60)
    migrated_topic = '{}/{}'.format(MIGRATED, end_user)
    topic = '{}/{}'.format(Constants.MONITOR_SERVICE, end_user)
    mqttClient.message_callback_add(migrated_topic, mqttClient.process_migrated)
    mqttClient.subscribe([(migrated_topic, 1)])
    mqttClient.loop_start()
    time.sleep(1)
    payload = json.dumps(monitor_msg_from_eu)
    start = time.time()
    mqttClient.publish(topic, payload)
    print("!!!Publish topic {} payload {}".format(topic, payload))
    while mqttClient.migrated_result is False and (time.time() - start) < timeout:
        time.sleep(0.001)
    print("Total time from trigger migration to return msg: {}".format(
        time.time() - start))
    assert mqttClient.migrated_result == True
    service_ip = mqttClient.migrated_service['ip']
    service_port = int(mqttClient.migrated_service['port'])
    mqttClient.disconnect()
    return service_ip, service_port
