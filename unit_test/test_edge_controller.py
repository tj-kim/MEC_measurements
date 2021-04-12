import os
import collections
import time
import json

import yaml
import mock
import docker
import pytest

from .. migrate_node import MigrateRecord
from .. network_monitor import MonitorReport
from .. edge_controller import ControllerServer
from .. container_monitor import ContainerReport
from .. utilities import find_my_ip, get_hostname
from .. import Constants
MQTTMsg = collections.namedtuple('MQTTMsg', ['topic', 'payload'])

@pytest.fixture(scope='module')
def edge(select_server):
    # Create a controller with rssi planner
    server = ControllerServer(select_server.ip,
                              select_server.port, distance=2)
    # Patch publish method with a mock function
    server.publish = mock.Mock()
    return server

@pytest.mark.incremental
class TestEdgeController(object):
    SERVER_NAME1 = get_hostname()
    SERVER_NAME2 = 'edge02'
    SERVER_NAME3 = 'edge03'
    USER_NAME = 'test_user'
    SERVICE_NAME = 'openface'
    SSID1 = "edge01-bts"
    SSID2 = "edge02-bts"
    BSSID1 = '51:3e:aa:49:98:cb'
    BSSID2 = '52:3e:aa:49:98:cb'
    IP1 = find_my_ip()
    IP2 = '172.18.38.157'
    IP3 = '172.18.33.42'

    def test_register_to_centre(self, edge):
        edge.publish = mock.Mock()
        edge.register_to_centre()
        assert edge.publish.called

    def test_process_updated_servers(self, edge):
        client = None
        userdata = None
        service_json = [
            {"ip": "172.18.37.105",
            "server_name": "LalaEdge1-OptiPlex-9020",
            "bs": "edge01"},
            {"ip": "172.18.38.111",
            "server_name": "LalaEdge2-OptiPlex-9020",
            "bs": "edge02"}]
        topic = Constants.UPDATED_SERVERS
        message = MQTTMsg(topic, json.dumps(service_json))
        edge.process_updated_servers(client, userdata, message)
        assert len(edge.my_neighbors.servers) == 2
        n = edge.my_neighbors.get_server_info("LalaEdge1-OptiPlex-9020")
        assert n['ip'] == "172.18.37.105"
        n2 = edge.my_neighbors.get_server_info("LalaEdge2-OptiPlex-9020")
        assert n2['ip'] == "172.18.38.111"

    def test_process_neighbor_off(self, edge):
        client = None
        userdata = None
        topic = '{}/{}'.format(Constants.LWT_EDGE,
            "LalaEdge2-OptiPlex-9020")
        message = MQTTMsg(topic, "Unexpected exit")
        edge.process_neighbor_off(client, userdata, message)
        assert len(edge.my_neighbors.servers) == 1
        n = edge.my_neighbors.get_server_info("LalaEdge1-OptiPlex-9020")
        assert n['ip'] == "172.18.37.105"
        n2 = edge.my_neighbors.get_server_info("LalaEdge2-OptiPlex-9020")
        assert n2 is None

    @mock.patch('docker.from_env')
    def test_process_deploy(self, mock_docker, edge):
        mock_docker.containers.get.side_effect = docker.errors.NotFound("Not found")
        client = None
        userdata = None
        user_name = TestEdgeController.USER_NAME
        topic = '{}/{}'.format(Constants.DEPLOY, user_name)
        service_json = {
                'end_user': user_name,
                'ssid': TestEdgeController.SSID1,
                'bssid': TestEdgeController.BSSID1,
                'service_name': 'openface',
                Constants.MIGRATE_METHOD: Constants.PRE_COPY
                }
        message = MQTTMsg(topic, json.dumps(service_json))
        edge.process_deploy(client, userdata, message)
        assert edge.publish.called
        edge_services = edge.edge_services.get_services_from_user(user_name)
        assert len(edge_services) == 1
        assert edge_services[0].server_name == TestEdgeController.SERVER_NAME1
        assert edge_services[0].end_user == user_name
        assert edge_services[0].service_name == 'openface'
        assert len(edge.edge_services.services) == 1

    def test_process_destroy_wrong_service(self, edge):
        edge.publish = mock.Mock()
        client = None
        userdata = None
        user_name = TestEdgeController.USER_NAME
        topic = '{}/{}'.format(Constants.DESTROY, user_name)
        service_json = {'container_img': 'ngovanmao/openface:15',
                'end_user': user_name,
                'ssid': TestEdgeController.SSID1,
                'bssid': TestEdgeController.BSSID1,
                'ip': TestEdgeController.IP1,
                'server_name': TestEdgeController.SERVER_NAME1,
                'service_name': 'yolo',
                'container_port': 9999,
                'method': 'delta',
                'port': ''
                }
        message = MQTTMsg(topic, json.dumps(service_json))
        edge.process_destroy(client, userdata, message)
        assert edge.publish.called == False
        assert len(edge.edge_services.services) == 1

    @mock.patch('docker.from_env')
    def test_process_destroy_deployed_service(self, mock_docker, edge):
        container = mock.Mock()
        mock_docker.containers.get.return_value = container
        container.status = 'running'
        client = None
        userdata = None
        user_name = TestEdgeController.USER_NAME
        topic = '{}/{}'.format(Constants.DESTROY, user_name)
        service_json = {'container_img': 'ngovanmao/openface:15',
                'end_user': user_name,
                'ssid': TestEdgeController.SSID1,
                'bssid': TestEdgeController.BSSID1,
                'ip': TestEdgeController.IP1,
                'server_name': TestEdgeController.SERVER_NAME1,
                'service_name': 'openface',
                'container_port': 9999,
                'method': 'delta',
                'port': ''
                }
        message = MQTTMsg(topic, json.dumps(service_json))
        edge.process_destroy(client, userdata, message)
        assert len(edge.edge_services.services) == 0

    def test_network_report(self, edge):
        edge.publish = mock.Mock()
        edge.network_report(MonitorReport(TestEdgeController.SERVER_NAME1,
                                          TestEdgeController.SERVER_NAME2,
                                          10, 100))
        assert edge.publish.called

    def test_migration_report_cb(self, edge):
        edge.publish = mock.Mock()
        service = '{}{}'.format(TestEdgeController.SERVICE_NAME,
                                TestEdgeController.USER_NAME)
        report = MigrateRecord(dest_ip=TestEdgeController.IP2, service=service,
                               pre_checkpoint=10, pre_rsync=10, checkpoint=10, rsync=10,
                               xdelta_source=10, final_rsync=10)
        edge.source_report_cb(report)
        assert edge.publish.called
        edge.publish = mock.Mock()
        report = MigrateRecord(source_ip=TestEdgeController.IP1, service=service,
                               restore=10)
        edge.dest_report_cb(report)
        assert edge.publish.called

    def test_container_report(self, edge):
        edge.publish = mock.Mock()
        edge.container_report(ContainerReport('{}{}'.\
                                              format(TestEdgeController.SERVICE_NAME,
                                              TestEdgeController.USER_NAME),
                                              'running', 0.1, 100, 400, 4096,
                                              572238034, 0, 0))
        assert edge.publish.called

