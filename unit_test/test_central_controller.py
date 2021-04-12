import os
import json
import subprocess
import collections

import pytest
import mock
import yaml
import time

from .. migrate_node import MigrateNode
from .. import Constants
from .. import central_database as db
from .. import centralized_controller as controller
from .. planner import PlanResult
from conftest import MQTTMsg

# Create a fresh database
DATABASE_NAME = 'test-centre'

@pytest.fixture(scope='module', params=[Constants.RANDOM_PLAN,
                                        Constants.NEAREST_PLAN,
                                        # Constants.OPTIMIZED_PLAN,
                                        Constants.CLOUD_PLAN])
def central(request, select_server):
    db_name = '{}-{}.db'.format(DATABASE_NAME, request.param)
    if os.path.exists(db_name):
        os.remove(db_name)
    database = db.DBCentral(database=db_name)
    # Create a controller with rssi planner
    server = controller.CentralizedController(select_server.ip,
        select_server.port, database, planner=request.param,
        migrate_method=Constants.PRE_COPY)
    # Patch publish method with a mock function
    server.publish = mock.Mock()
    yield server
    server.db.close()

def convert_name_to_bts(name):
    return '{}-bts'.format(name)

@pytest.mark.incremental
class TestCentralController(object):
    CLOUD_NAME = 'centre'
    SERVER_NAME1 = 'edge01'
    SERVER_NAME2 = 'edge02'
    SERVER_NAME3 = 'edge03'
    USER_NAME = 'test_user'
    SERVICE_NAME = 'openface'
    BSSID = '51:3e:aa:49:98:cb'
    BSSID2 = '52:3e:aa:49:98:cb'
    IP_CLOUD = '172.18.35.76'
    IP1 = '172.18.37.105'
    IP2 = '172.18.38.157'
    IP3 = '172.18.33.42'

    def test_register_edge(self, central):
        database = central.db
        client = None
        userdata = None
        name = TestCentralController.SERVER_NAME1
        ip = '172.18.37.105'
        distance = 2
        message = MQTTMsg("dummy",
                          json.dumps({'server_name': name,
                                      'ip': ip,
                                      'distance':distance,
                                      'port':9889,
                                      'bs': convert_name_to_bts(name),
                                      'phi':0.527,
                                      'rho':5.987}))
        central.process_edge_register(client, userdata, message)
        assert database.session.query(db.EdgeServerInfo.ip).\
               filter(db.EdgeServerInfo.name == name).scalar() == ip
        assert database.session.query(db.BTSInfo.name).\
            filter(db.BTSInfo.server_id == name).scalar() == \
            convert_name_to_bts(name)
        assert database.session.query(db.EdgeServerInfo.distance).\
               filter(db.EdgeServerInfo.name == name).scalar() == distance
        ip = '172.18.38.157'
        name = 'edge02'
        message = MQTTMsg("dummy",
                          json.dumps({'server_name': name,
                                      'ip': ip,
                                      'distance':distance,
                                      'port':9889,
                                      'bs': convert_name_to_bts(name),
                                      'phi':0.527,
                                      'rho':5.987}))
        central.process_edge_register(client, userdata, message)
        ip = '172.18.33.42'
        name = 'edge03'
        message = MQTTMsg(Constants.REGISTER,
                          json.dumps({'server_name': name,
                                      'ip': ip,
                                      'distance':distance,
                                      'port':9889,
                                      'bs': convert_name_to_bts(name),
                                      'phi':0.527,
                                      'rho':5.987}))
        central.process_edge_register(client, userdata, message)
        central.publish = mock.Mock()
        message = MQTTMsg(Constants.REGISTER,
                          json.dumps({'server_name': TestCentralController.CLOUD_NAME,
                                      'ip': TestCentralController.IP_CLOUD,
                                      'distance':0,
                                      'port':9889,
                                      'phi':0.527,
                                      'rho':5.987}))
        central.process_edge_register(client, userdata, message)
        assert central.publish.called
        topic, payload = central.publish.call_args[0]
        payload_json = yaml.safe_load(payload)
        with pytest.raises(KeyError) as e_info:
            for s in payload_json:
                if s['server_name'] == TestCentralController.CLOUD_NAME:
                    s['bs']

    def test_process_edge_monitor(self, central):
        database = central.db
        client = None
        userdata = None
        last_cnt = database.session.query(db.NetworkRecord).count()
        servers = [(TestCentralController.CLOUD_NAME, TestCentralController.IP_CLOUD),
                   (TestCentralController.SERVER_NAME1, TestCentralController.IP1),
                   (TestCentralController.SERVER_NAME2, TestCentralController.IP2),
                   (TestCentralController.SERVER_NAME3, TestCentralController.IP3)]
        for src in servers:
            for dst in servers:
                if src == dst:
                    continue
                topic = '{}/{}'.format(Constants.MONITOR_EDGE, src[0])
                message = MQTTMsg(topic,
                    json.dumps({'src_node': src[1],
                                'dest_node': dst[1],
                                'latency': 10,
                                'bw': 100}))
                central.process_edge_monitor(client, userdata, message)
        new_cnt = database.session.query(db.NetworkRecord).count()
        assert last_cnt + len(servers)*(len(servers)-1) == new_cnt

    def test_process_edge_monitor_error(self, central):
        database = central.db
        client = None
        userdata = None
        last_cnt = database.session.query(db.NetworkRecord).count()
        topic = '{}/{}'.format(Constants.MONITOR_EDGE,
                               TestCentralController.SERVER_NAME1)
        message = MQTTMsg(topic,
                    json.dumps({'src_node': TestCentralController.SERVER_NAME2,
                                'dest_node': TestCentralController.SERVER_NAME3,
                                'latency': 10,
                                'bw': 100}))
        central.process_edge_monitor(client, userdata, message)
        new_cnt = database.session.query(db.NetworkRecord).count()
        assert last_cnt == new_cnt

    def test_process_edge_status_report(self, central):
        database = central.db
        client = None
        userdata = None
        topic = '{}/{}'.format(Constants.MONITOR_SERVER,
                               TestCentralController.SERVER_NAME1)
        message = MQTTMsg(topic,
                          json.dumps({
                              'cpu_max': 3600,
                              'cpu_cores': 8,
                              'mem_total': 16000,
                              'mem_free': 4000,
                              'disk_total': 500,
                              'disk_free': 40
                          }))
        central.process_monitor_server_status(client, userdata, message)
        obj = database.session.query(db.EdgeServerInfo).\
            filter(db.EdgeServerInfo.name==TestCentralController.SERVER_NAME1).\
              first()
        assert obj.max_cpu == 3600
        assert obj.core_cpu == 8
        servers = [TestCentralController.CLOUD_NAME,
                   TestCentralController.SERVER_NAME2,
                   TestCentralController.SERVER_NAME3]
        for s in servers:
            topic = '{}/{}'.format(Constants.MONITOR_SERVER, s)
            message = MQTTMsg(topic,
                              json.dumps({
                                  'cpu_max': 3600,
                                  'cpu_cores': 8,
                                  'mem_total': 16000,
                                  'mem_free': 4000,
                                  'disk_total': 500,
                                  'disk_free': 40}))
            central.process_monitor_server_status(client, userdata, message)

    def test_discovery(self, central):
        database = central.db
        client = None
        userdata = None
        name = Constants.YOLO
        user = TestCentralController.USER_NAME
        message = MQTTMsg(Constants.DISCOVER,
                          json.dumps({
                              'service_name': name,
                              Constants.END_USER: user,
                              Constants.ASSOCIATED_SSID: convert_name_to_bts(
                                  TestCentralController.SERVER_NAME1),
                              Constants.ASSOCIATED_BSSID: TestCentralController.BSSID
                          }))
        central.process_discovery(client, userdata, message)
        topic, payload = central.publish.call_args[0]
        assert topic is not None
        assert payload is not None
        yaml.safe_load(payload)
        assert database.session.query(db.EndUserInfo.bts).\
            filter(db.EndUserInfo.name == user).scalar() == \
            convert_name_to_bts(TestCentralController.SERVER_NAME1)
        assert central.db.est_time_users[user] is not None

    # Allocate user= test_user to edge01-bts and edge01 server
    def test_process_allocated(self, central):
        database = central.db
        client = None
        userdata = None
        user = TestCentralController.USER_NAME
        service_json = {'container_img': Constants.YOLO_DOCKER_IMAGE,
                        Constants.END_USER: user,
                        Constants.SERVER_NAME: TestCentralController.SERVER_NAME1,
                        Constants.ASSOCIATED_SSID: convert_name_to_bts(
                            TestCentralController.SERVER_NAME1),
                        Constants.ASSOCIATED_BSSID: TestCentralController.BSSID,
                        'ip': '10.0.99.10',
                        'container_port': 9999, 'method': 'delta',
                        'snapshot': 'snapshot', 'registry': 'ngovanmao',
                        'dump_dir': '/tmp', 'service_name': Constants.YOLO,
                        'debug': True, 'port': 9900, 'user': 'root'}
        message = MQTTMsg('dummy',
                          json.dumps(service_json))
        central.process_allocated(client, userdata, message)
        assert database.session.query(db.ServiceInfo.name).\
            filter(db.ServiceInfo.container_img == service_json['container_img']).\
            scalar() is not None
        assert database.get_service(user).server_name == \
            TestCentralController.SERVER_NAME1
        save_service = database.get_service(user)
        assert save_service.container_port == 9999
        assert save_service.port == 9900
        # Test get_json
        assert save_service.get_json()[Constants.SERVER_NAME] == \
            TestCentralController.SERVER_NAME1

    def test_discovery_duplicate(self, central):
        database = central.db
        central.publish = mock.Mock()
        client = None
        userdata = None
        name = Constants.YOLO
        user = TestCentralController.USER_NAME
        message = MQTTMsg(Constants.DISCOVER,
                          json.dumps({
                              'service_name': name,
                              Constants.END_USER: user,
                              Constants.ASSOCIATED_SSID: convert_name_to_bts(
                                  TestCentralController.SERVER_NAME1),
                              Constants.ASSOCIATED_BSSID: TestCentralController.BSSID
                          }))
        central.process_discovery(client, userdata, message)
        topic, payload = central.publish.call_args[0]
        assert Constants.DEPLOY in topic
        assert payload is not None
        yaml.safe_load(payload)
        assert database.session.query(db.EndUserInfo.bts).\
            filter(db.EndUserInfo.name == user).scalar() == \
            convert_name_to_bts(TestCentralController.SERVER_NAME1)

    def test_process_allocated_duplicate(self, central):
        database = central.db
        client = None
        userdata = None
        user = TestCentralController.USER_NAME
        service_json = {'container_img': Constants.YOLO_DOCKER_IMAGE,
                        Constants.END_USER: user,
                        Constants.SERVER_NAME: TestCentralController.SERVER_NAME1,
                        Constants.ASSOCIATED_SSID: convert_name_to_bts(
                            TestCentralController.SERVER_NAME1),
                        Constants.ASSOCIATED_BSSID: TestCentralController.BSSID,
                        'ip': '10.0.99.10',
                        'container_port': 9999, 'method': 'delta',
                        'snapshot': 'snapshot', 'registry': 'ngovanmao',
                        'dump_dir': '/tmp', 'service_name': Constants.YOLO,
                        'debug': True, 'port': 9900, 'user': 'root'}
        message = MQTTMsg('dummy',
                          json.dumps(service_json))
        central.process_allocated(client, userdata, message)
        assert database.session.query(db.ServiceInfo.name).\
            filter(db.ServiceInfo.container_img == service_json['container_img']).\
            scalar() is not None
        assert database.get_service(user).server_name == \
            TestCentralController.SERVER_NAME1
        save_service = database.get_service(user)
        assert save_service.container_port == 9999
        assert save_service.port == 9900
        # Test get_json
        assert save_service.get_json()[Constants.SERVER_NAME] == \
            TestCentralController.SERVER_NAME1

    def test_user_send_discovery_again(self, central):
        database = central.db
        central.publish = mock.Mock()
        client = None
        userdata = None
        name = TestCentralController.SERVICE_NAME
        user = TestCentralController.USER_NAME
        message = MQTTMsg(Constants.DISCOVER,
                          json.dumps({
                              'service_name': name,
                              Constants.END_USER: user,
                              Constants.ASSOCIATED_SSID: convert_name_to_bts(
                                  TestCentralController.SERVER_NAME1),
                              Constants.ASSOCIATED_BSSID:TestCentralController.BSSID
                          }))
        central.process_discovery(client, userdata, message)
        assert central.publish.called
        topic, payload = central.publish.call_args_list[0][0]
        payload_json = yaml.safe_load(payload)
        assert Constants.DESTROY in topic
        assert payload_json[Constants.END_USER] == user
        topic, payload = central.publish.call_args_list[1][0]
        payload_json = yaml.safe_load(payload)
        assert Constants.DEPLOY in topic
        assert payload_json[Constants.END_USER] == user
        assert database.session.query(db.EndUserInfo.bts).\
            filter(db.EndUserInfo.name == user).scalar() == \
            convert_name_to_bts(TestCentralController.SERVER_NAME1)

    def test_server_process_allocated_again(self, central):
        database = central.db
        client = None
        userdata = None
        user = TestCentralController.USER_NAME
        service_json = {'container_img': 'ngovanmao/openface:12',
                        Constants.END_USER: user,
                        Constants.ASSOCIATED_SSID: convert_name_to_bts(
                            TestCentralController.SERVER_NAME1),
                        Constants.ASSOCIATED_BSSID: TestCentralController.BSSID,
                        'ip': '10.0.99.10',
                        Constants.SERVER_NAME: TestCentralController.SERVER_NAME1,
                        'container_port': 9999, 'method': 'delta',
                        'snapshot': 'snapshot', 'registry': 'ngovanmao',
                        'dump_dir': '/tmp', 'service_name': 'openface',
                        'debug': True, 'port': 9900, 'user': 'root'}
        message = MQTTMsg('dummy',
                          json.dumps(service_json))
        central.process_allocated(client, userdata, message)
        assert database.session.query(db.ServiceInfo.name).\
            filter(db.ServiceInfo.container_img == service_json['container_img']).\
            scalar() is not None
        assert database.get_service(user).server_name == \
            TestCentralController.SERVER_NAME1
        save_service = database.get_service(user)
        assert save_service.container_port == 9999
        assert save_service.port == 9900
        # Test get_json
        assert save_service.get_json()[Constants.SERVER_NAME] == \
            TestCentralController.SERVER_NAME1

    def test_process_container_monitor(self, central):
        database = central.db
        client = None
        userdata = None
        service = '{}{}'.format(TestCentralController.SERVICE_NAME,
                                TestCentralController.USER_NAME)
        message = MQTTMsg('{}/{}'.format(Constants.MONITOR_CONTAINER,
                                         TestCentralController.SERVER_NAME1),
                          json.dumps({
                              'container' : service,
                              'status' : 'running',
                              'cpu' : 0.01,
                              'mem' : 1000,
                              'size' : 200,
                              'delta_memory': 12.3,
                              'pre_checkpoint': 50*10**6, # B
                              'time_xdelta': 2.5, #s
                              'time_checkpoint': 0.7 #s
                          }))
        central.process_monitor_container(client, userdata, message)
        obj = database.session.query(db.ServiceInfo).\
              filter(db.ServiceInfo.name == service).first()
        assert obj.status == 'running'

    def test_process_monitor_eu_without_migrate(self, central):
        database = central.db
        central.publish = mock.Mock()
        client = None
        userdata = None
        service_name = TestCentralController.SERVICE_NAME
        user = TestCentralController.USER_NAME
        monitor_msg_from_eu = {
            Constants.END_USER : user,
            'serviceName': service_name,
            'nearbyAP': [
                {Constants.SSID: convert_name_to_bts(
                     TestCentralController.SERVER_NAME1),
                 Constants.BSSID: TestCentralController.BSSID,
                 Constants.RSSI: -45},
                {'SSID': 'edge03-bts',
                 'BSSID': '86:16:f9:0f:b5:ce',
                 'level': -50},
            ]}
        topic = '{}/{}'.format(Constants.MONITOR_EU, user)
        message = MQTTMsg(topic,
                          json.dumps(monitor_msg_from_eu))
        central.process_monitor_eu(client, userdata, message)
        if central.planner_type == Constants.OPTIMIZED_PLAN:
            T_pre_mig_avg, lifetime = central.planner.lifetime_to_average_pre_mig(user)
            assert lifetime == 1000
        assert central.publish.called is False

    def test_process_monitor_service_without_migrate(self, central):
        database = central.db
        central.publish = mock.Mock()
        # central.trigger_handover_migration = mock.Mock()
        client = None
        userdata = None
        service_name = TestCentralController.SERVICE_NAME
        user = TestCentralController.USER_NAME
        monitor_msg_from_eu = {
            Constants.END_USER : user,
            Constants.SERVICE_NAME: service_name,
            Constants.ASSOCIATED_SSID: 'edge01-bts',
            Constants.ASSOCIATED_BSSID:'52:3e:aa:49:98:cb',
            'startTime[ns]':3685422149965579,
            'endTime[ns]':3685422655153495,
            'processTime[ms]':461.27978515625,
            'sentSize[B]':5765}
        topic = '{}/{}'.format(Constants.MONITOR_SERVICE, user)
        message = MQTTMsg(topic,
                          json.dumps(monitor_msg_from_eu))
        central.process_monitor_service(client, userdata, message)
        assert database.query_eu_data_size(user) == 5765
        assert database.query_number_request(user) == 1

    # migrate user test_user to bts: edge03-bts, server edge03
    def test_process_monitor_eu_with_migrate(self, central):
        database = central.db
        central.publish = mock.Mock()
        client = None
        userdata = None
        service_name = TestCentralController.SERVICE_NAME
        user = TestCentralController.USER_NAME
        monitor_msg_from_eu = {
            Constants.END_USER : user,
            'serviceName': service_name,
            'nearbyAP': [
                {Constants.SSID: convert_name_to_bts(
                     TestCentralController.SERVER_NAME1),
                 Constants.BSSID: TestCentralController.BSSID,
                 Constants.RSSI: Constants.RSSI_THRESHOLD - 1},
                {'SSID': convert_name_to_bts(
                    TestCentralController.SERVER_NAME3),
                 'BSSID': '86:16:f9:0f:b5:ce',
                 'level': -60},
            ] }
        topic = '{}/{}'.format(Constants.MONITOR_EU, user)
        message = MQTTMsg(topic,
                          json.dumps(monitor_msg_from_eu))
        central.process_monitor_eu(client, userdata, message)
        # wait to catch all MQTT publishes
        time.sleep(1)
        #print("calls... {}".format(central.publish.call_args_list))
        if central.planner_type == Constants.NEAREST_PLAN:
            assert central.publish.called is True
            for pub in central.publish.call_args_list:
                topic, payload = pub[0]
                assert Constants.PRE_MIGRATE in topic\
                    or Constants.MIGRATE in topic\
                    or Constants.HANDOVER in topic
                assert payload is not None
                payload_json = yaml.safe_load(payload)
                if Constants.PRE_MIGRATE in topic or\
                    Constants.MIGRATE in topic:
                    assert payload_json[Constants.SERVER_NAME]==\
                        TestCentralController.SERVER_NAME3
                    assert payload_json['ip'] ==\
                        TestCentralController.IP3
                if Constants.HANDOVER in topic:
                    assert payload_json[Constants.NEXT_SSID]==\
                        convert_name_to_bts(TestCentralController.SERVER_NAME3)
            assert central.migrating_plan.get(user, None) is None
        elif central.planner_type == Constants.RANDOM_PLAN:
            assert central.publish.called is True
            for pub in central.publish.call_args_list:
                topic, payload = pub[0]
                assert Constants.PRE_MIGRATE in topic\
                    or Constants.MIGRATE in topic\
                    or Constants.HANDOVER in topic
                assert payload is not None
                payload_json = yaml.safe_load(payload)
                if Constants.HANDOVER in topic:
                    assert payload_json[Constants.NEXT_SSID]==\
                        convert_name_to_bts(TestCentralController.SERVER_NAME3)
        elif central.planner_type == Constants.OPTIMIZED_PLAN:
            assert central.publish.called is False
        elif central.planner_type == Constants.CLOUD_PLAN:
            assert central.publish.called is True
        else:
            pytest.fail("Unknow planner")

    def generate_service_json(self, end_user, service_name, server_name, ip,
        ssid, bssid):
        service_json = {
            'container_img': 'ngovanmao/openface:12',
            Constants.END_USER: end_user,
            Constants.ASSOCIATED_SSID: ssid,
            Constants.BSSID: bssid,
            Constants.SERVER_NAME: server_name,
            'ip': ip, 'container_port': 9999,
            'method': 'delta', 'snapshot': 'snapshot',
            'registry':'ngovanmao', 'dump_dir': '/tmp',
            'service_name': service_name, 'port':9901, 'user': 'root'
        }
        return service_json

    def test_process_pre_migrated(self, central):
        database = central.db
        central.publish = mock.Mock()
        client = None
        userdata = None
        end_user = TestCentralController.USER_NAME
        service_name = TestCentralController.SERVICE_NAME
        old_ssid = convert_name_to_bts(TestCentralController.SERVER_NAME1)
        old_bssid = TestCentralController.BSSID
        new_ssid = convert_name_to_bts(TestCentralController.SERVER_NAME3)
        new_bssid = TestCentralController.BSSID
        old_server_name = TestCentralController.SERVER_NAME1
        new_server_name = TestCentralController.SERVER_NAME3
        old_service_json = self.generate_service_json(end_user, service_name,
            TestCentralController.IP1,
            old_server_name, old_ssid, old_bssid)
        if central.planner_type == Constants.NEAREST_PLAN or \
            central.planner_type == Constants.RANDOM_PLAN or \
            central.planner_type == Constants.CLOUD_PLAN:
            assert True
        elif central.planner_type == Constants.OPTIMIZED_PLAN:
            central.db.est_time_users[end_user].update_time(old_server_name,
                new_server_name, 10, 0)
            #print("estimate times {}".format(central.db.est_time_users[end_user].__dict__))
            # fake update service to old assign
            old_service = MigrateNode(**old_service_json)
            state = Constants.PRE_MIGRATE
            central.db.update_service(old_service, state)
            # new service
            new_service_json = self.generate_service_json(end_user, service_name,
                TestCentralController.IP3,
                new_server_name, new_ssid, new_bssid)
            fake_assign = (new_ssid, new_server_name)
            plan = PlanResult(end_user, *fake_assign)
            if central.migrating_plan.get(end_user, None) is None:
                stored_obj = {'plan':plan,'service':new_service_json}
                central.migrating_plan[end_user] = stored_obj
            message = MQTTMsg('{}/{}'.format(Constants.PRE_MIGRATED,
                                old_server_name),
                              json.dumps(new_service_json))
            central.process_pre_migrated(client, userdata, message)
            assert True
        else:
            pytest.fail("Unknow planner")

    # Now migrated to edge03 and edge03-bts
    def test_process_migrated(self, central):
        database = central.db
        central.publish = mock.Mock()
        client = None
        userdata = None
        migrate_msg = {
            'container_img': 'ngovanmao/openface:12',
            Constants.END_USER: TestCentralController.USER_NAME,
            Constants.ASSOCIATED_SSID: convert_name_to_bts(
                TestCentralController.SERVER_NAME3),
            Constants.ASSOCIATED_BSSID: TestCentralController.BSSID,
            Constants.SERVER_NAME: TestCentralController.SERVER_NAME3,
            'ip': '172.18.37.105', 'container_port': 9999,
            'method': 'delta', 'snapshot': 'snapshot',
            'registry':'ngovanmao', 'dump_dir': '/tmp',
            'service_name': 'openface', 'port':9901, 'user': 'root'
        }
        topic = '{}/{}'.format(Constants.MIGRATED,\
            TestCentralController.SERVER_NAME1)
        message = MQTTMsg(topic, json.dumps(migrate_msg))
        central.process_migrated(client, userdata, message)
        save_service = database.get_service(TestCentralController.USER_NAME)
        assert save_service.container_port == 9999
        assert save_service.port == 9901
        # Test get_json
        assert save_service.get_json()[Constants.SERVER_NAME] == \
            TestCentralController.SERVER_NAME3

    def test_process_handovered(self, central):
        database = central.db
        central.publish = mock.Mock()
        client = None
        userdata = None
        end_user = TestCentralController.USER_NAME
        handovered_msg = {
            Constants.ASSOCIATED_SSID: convert_name_to_bts(
                TestCentralController.SERVER_NAME3),
            Constants.ASSOCIATED_BSSID: TestCentralController.BSSID
            }
        topic = '{}/{}'.format(Constants.HANDOVERED, end_user)
        message = MQTTMsg(topic, json.dumps(handovered_msg))
        central.process_handovered(client, userdata, message)
        user_info = database.get_user(end_user)
        assert user_info.bts == convert_name_to_bts(
            TestCentralController.SERVER_NAME3)

    def test_process_monitor_service_without_migrate_2(self, central):
        database = central.db
        central.publish = mock.Mock()
        # central.trigger_handover_migration = mock.Mock()
        client = None
        userdata = None
        service_name = TestCentralController.SERVICE_NAME
        user = TestCentralController.USER_NAME
        monitor_msg_from_eu = {
            Constants.END_USER : user,
            Constants.SERVICE_NAME: service_name,
            Constants.ASSOCIATED_SSID: 'edge03-bts',
            Constants.ASSOCIATED_BSSID:'52:3e:aa:49:98:cb',
            'startTime[ns]':3685422149965579,
            'endTime[ns]':3685422655153495,
            'processTime[ms]':461.27978515625, # make sure tran < 50ms
            'sentSize[B]':5765}
        topic = '{}/{}'.format(Constants.MONITOR_SERVICE, user)
        message = MQTTMsg(topic,
                          json.dumps(monitor_msg_from_eu))
        central.process_monitor_service(client, userdata, message)
        assert database.query_eu_data_size(user) == 5765
        # this no_request was reset to zero after migration
        assert database.query_number_request(user) == 1

    # test again to provide information for estimate time
    def test_process_container_monitor_2(self, central):
        database = central.db
        client = None
        userdata = None
        service = '{}{}'.format(TestCentralController.SERVICE_NAME,
                                TestCentralController.USER_NAME)
        message = MQTTMsg('{}/{}'.format(Constants.MONITOR_CONTAINER,
                                         TestCentralController.SERVER_NAME3),
                          json.dumps({
                              'container' : service,
                              'status' : 'running',
                              'cpu' : 0.01,
                              'mem' : 1000,
                              'size' : 200,
                              'delta_memory': 12.3,
                              'pre_checkpoint': 50*10**6, # B
                              'time_xdelta': 2.5, #s
                              'time_checkpoint': 0.7 #s
                          }))
        central.process_monitor_container(client, userdata, message)
        obj = database.session.query(db.ServiceInfo).\
              filter(db.ServiceInfo.name == service).first()
        assert obj.status == 'running'


    def test_process_monitor_service_with_migrate(self, central):
        database = central.db
        # central.trigger_handover_migration = mock.Mock()
        central.publish = mock.Mock()
        client = None
        userdata = None
        service_name = TestCentralController.SERVICE_NAME
        user = TestCentralController.USER_NAME
        cur_assign = database.query_cur_assign(user)
        #print("current assign {}".format(cur_assign))
        monitor_msg_from_eu = {
            Constants.END_USER : user,
            Constants.SERVICE_NAME: service_name,
            Constants.ASSOCIATED_SSID: 'edge03-bts',
            Constants.ASSOCIATED_BSSID:'52:3e:aa:49:98:cb',
            'startTime[ns]':3685421149965579,
            'endTime[ns]':3685422655153495, # E2E delay=1505ms
            'processTime[ms]':301.27978515625, # trans_delay = 1203ms
            'sentSize[B]':5765}
        topic = '{}/{}'.format(Constants.MONITOR_SERVICE, user)
        message = MQTTMsg(topic,
                          json.dumps(monitor_msg_from_eu))
        central.process_monitor_service(client, userdata, message)
        assert database.query_eu_data_size(user) == 5765
        assert database.query_number_request(user) == 2
        # assert central.trigger_handover_migration.called

    def test_process_edge_notification(self, central):
        database = central.db
        central.publish = mock.Mock()
        client = None
        userdata = None
        message = MQTTMsg('{}/{}'.format(Constants.LWT_EDGE,
                                         TestCentralController.SERVER_NAME1),
                          "Unexpected exit")
        services = database.get_service_with_server(TestCentralController.SERVER_NAME1)
        central.process_edge_notification(client, userdata, message)
        if len(services) != 0:
            assert central.publish.called is True
        else:
            assert central.publish.called is False

    def test_reconnect_edge(self, central):
        database = central.db
        client = None
        userdata = None
        name = TestCentralController.SERVER_NAME1
        ip = '172.18.37.105'
        message = MQTTMsg(Constants.REGISTER,
                          json.dumps({'server_name': name,
                                      'ip': ip,
                                      'port':9889,
                                      'distance':2,
                                      'bs': convert_name_to_bts(name)}))
        central.process_edge_register(client, userdata, message)
        assert database.session.query(db.EdgeServerInfo.ip).\
               filter(db.EdgeServerInfo.name == name).scalar() == ip
        assert database.session.query(db.BTSInfo.name).\
            filter(db.BTSInfo.server_id == name).scalar() == convert_name_to_bts(name)

    def test_process_edge_status_report_again(self, central):
        ''' This test case tends to update server information after leaving
        and reconnect.
        '''
        database = central.db
        client = None
        userdata = None
        topic = '{}/{}'.format(Constants.MONITOR_SERVER,
                               TestCentralController.SERVER_NAME1)
        message = MQTTMsg(topic,
                          json.dumps({
                              'cpu_max': 3600,
                              'cpu_cores': 8,
                              'mem_total': 16000,
                              'mem_free': 4000,
                              'disk_total': 500,
                              'disk_free': 40
                          }))
        central.process_monitor_server_status(client, userdata, message)
        obj = database.session.query(db.EdgeServerInfo).\
            filter(db.EdgeServerInfo.name==TestCentralController.SERVER_NAME1).\
              first()
        assert obj.max_cpu == 3600
        assert obj.core_cpu == 8
        servers = [TestCentralController.CLOUD_NAME,
                   TestCentralController.SERVER_NAME2,
                   TestCentralController.SERVER_NAME3]
        for s in servers:
            topic = '{}/{}'.format(Constants.MONITOR_SERVER, s)
            message = MQTTMsg(topic,
                              json.dumps({
                                  'cpu_max': 3600,
                                  'cpu_cores': 8,
                                  'mem_total': 16000,
                                  'mem_free': 4000,
                                  'disk_total': 500,
                                  'disk_free': 40}))
            central.process_monitor_server_status(client, userdata, message)


    def test_migrate_report(self, central):
        database = central.db
        client = None
        userdata = None
        test_service='{}{}'.format(TestCentralController.SERVICE_NAME,
                                   TestCentralController.USER_NAME)
        # TODO: Change the numbers in test case to more realistic numbers
        message_source = MQTTMsg('{}/{}/{}'.format(Constants.MIGRATE_REPORT,
                                 'source',
                                 TestCentralController.SERVER_NAME1),
            json.dumps({'source': TestCentralController.SERVER_NAME1,
                        'dest': TestCentralController.SERVER_NAME2,
                        'service': test_service,
                        'method': 'xdelta',
                        'pre_checkpoint':'0.7453069686889648',
                        'pre_rsync':1.3106780052185059,
                        'prepare': 20,
                        'checkpoint': 10,
                        'rsync': 10,
                        'xdelta_source': 10,
                        'final_rsync': 1.6011459827423096,
                        'migrate':10,
                        'premigration':10,
                        'size_pre_rsync':10,
                        'size_rsync':'732336',
                        'size_final_rsync':'1538523'}))
        message_dest = MQTTMsg('{}/{}/{}'.format(Constants.MIGRATE_REPORT,
                               'dest',
                               TestCentralController.SERVER_NAME2),
            json.dumps({'source': TestCentralController.SERVER_NAME1,
                        'dest': TestCentralController.SERVER_NAME2,
                        'service': test_service,
                        'restore': 10,
                        'xdelta_dest':10}))
        central.process_migrate_report(client, userdata, message_source)
        central.process_migrate_report(client, userdata, message_dest)
        assert database.session.query(db.MigrateRecord).count() == 1
        obj = database.session.query(db.MigrateRecord).first()
        assert obj.restore == 10

    def test_failed_migrate_report(self, central):
        database = central.db
        client = None
        userdata = None
        test_service='{}{}'.format(TestCentralController.SERVICE_NAME,
                                   TestCentralController.USER_NAME)
        # TODO: Change the numbers in test case to more realistic numbers
        message_dest = MQTTMsg('{}/{}/{}'.format(Constants.MIGRATE_REPORT,
                                                 'dest',
                                                 TestCentralController.SERVER_NAME2),
                               json.dumps({'source': TestCentralController.SERVER_NAME1,
                                           'dest': TestCentralController.SERVER_NAME2,
                                           'service': test_service,
                                           'xdelta_dest': 10,
                                           'restore': 10}))
        central.process_migrate_report(client, userdata, message_dest)
        assert database.session.query(db.MigrateRecord).count() == 1

    def test_process_eu_notification(self, central):
        database = central.db
        central.publish = mock.Mock()
        client = None
        userdata = None
        message = MQTTMsg('{}/{}'.format(Constants.LWT_EU,
                                         TestCentralController.USER_NAME),
                          "Unexpected exit")
        central.process_eu_notification(client, userdata, message)
        assert central.publish.called is True
        topic, payload = central.publish.call_args[0]
        payload_json = yaml.safe_load(topic)

