from __future__ import division

import os
import time
import logging
import threading

from pytest import approx
import pytest
import sqlalchemy
from sqlalchemy import func
import collections
import math
import numpy as np

from .. import central_database as db
from .. central_database import get_time
from .. import Constants
from .. central_database import get_exp_moving_average, build_linear_regression

from .. discovery_edge import DiscoveryYaml

BTSInfo = collections.namedtuple('BTSInfo', ['name', 'bssid', 'passwd', 'server',
                                             'x', 'y'])
def log_rssi_model(d, n=3, A=30):
    # RSSI = -(10*n*log(d) + A), log base 10
    if d < 1:
        d = 1
    #rssi = int(-(10*n*math.log10(d) + A))
    rssi = (-(10*n*math.log10(d) + A))
    return rssi

def generate_rssi_report(x, y, btss):
    ret = []
    for bts in btss:
        d = math.sqrt((x-bts.x)**2 + (y-bts.y)**2)
        rssi = log_rssi_model(d)
        ret.append({
            'SSID':bts.name,
            'BSSID': bts.bssid,
            'level': rssi
            })
    return ret

def theorecal_handover(x0, v, x_src, x_dst, r, hys=7.0, n=3):
    omega = 10**(hys/5/n)
    coeffs = [ 1 - omega,
               -2*(x_src - omega*x_dst),
               x_src**2 - omega*x_dst**2 + (1 - omega)*r**2 ]
    roots = sorted(np.roots(coeffs))
    logging.info("Roots for x0={}: {}".format(x0, roots))
    if not all(np.isreal(roots)):
        logging.error("Cannot found real solution ({})".format(roots))
        raise RuntimeError("Invalid parameter")
    x_ho = next((i for i in roots if i>x0), None)
    if x_ho is None:
        logging.error("Cannot found any future solution ({})".\
                      format(roots))
        raise RuntimeError("Invalid parameter")
    t_ho = (x_ho - x0)/v
    return t_ho

def test_get_exp_moving_average():
    rssi = -57
    RSSI = None
    new_RSSI = get_exp_moving_average(rssi, RSSI)
    assert new_RSSI == rssi
    rssi = -59
    RSSI = get_exp_moving_average(rssi, new_RSSI)
    assert RSSI > rssi

def test_build_linear_regression():
    ts = [2]
    RSSIs = [-57]
    eta, R = build_linear_regression(ts, RSSIs)
    assert eta is None
    ts = [2, 4]
    RSSIs = [-57, -60]
    eta, R = build_linear_regression(ts, RSSIs)
    print("eta {}, R {}".format(eta, R))
    assert eta < 0
    ts = [2, 4, 7]
    RSSIs = [-57, -60, -69]
    eta, R = build_linear_regression(ts, RSSIs)
    print("eta {}, R {}".format(eta, R))
    assert eta < 0


@pytest.fixture(scope="module")
def database():
    # Create a temporary database in RAM
    db_name = 'unit-test-central.db'
    if os.path.isfile(db_name):
        os.remove(db_name)
    test_db = db.DBCentral(database=db_name)
    yield test_db
    test_db.close()

def test_tables(database):
    obj_migrate_record = db.MigrateRecord(timestamp=get_time(), source='src',
                                          dest='dst', pre_checkpoint=1.0,
                                          service='test_test',
                                          pre_rsync=1.0, checkpoint=1.0,
                                          rsync=1.0, xdelta_source=1.0,
                                          final_rsync=1.0, restore=1.0,
                                          size_final_rsync=1.0)
    database.insert_obj(obj_migrate_record)
    obj_user_service = db.EndUserService(timestamp=get_time(),user_id='test',
                           service_id='test', ssid='test',
                           bssid='52:3e:aa:49:98:cb',
                           server_name='test_server', proc_delay=9.0,
                           request_size=100, e2e_delay=300.2)
    database.insert_obj(obj_user_service)
    obj_network_record = db.NetworkRecord(timestamp=get_time(),
                                          src_node='source', dest_node='dest',
                                          latency=10.0, bw=100)
    database.insert_obj(obj_network_record)
    obj_edge_info = db.EdgeServerInfo(name='test_server',ip='127.0.0.1', distance=2,
                        core_cpu=8, max_cpu=2e9, ram=10e9, disk=500e9,
                        phi=0.02,rho=0.08)
    database.insert_obj(obj_edge_info)
    obj_user_info = db.EndUserInfo(name='test', bts='test01', status=True)
    database.insert_obj(obj_user_info)

def thread_handler():
    my_db = db.DBCentral(database='unit-test-central.db')
    time.sleep(1)
    assert my_db.session.query(db.MigrateRecord).count() == 0
    time.sleep(1)

@pytest.mark.skip(reason='No applicable to Sqlite database')
def test_multiple_thread(database):
    th1 = threading.Thread(target=thread_handler)
    th2 = threading.Thread(target=thread_handler)
    th1.setDaemon(True)
    th2.setDaemon(True)
    th1.start()
    th2.start()
    th1.join()
    th2.join()


def test_add_large_number(database):
    for i in range(200):
        entry = db.EndUserService(timestamp=get_time(),
                                  user_id='test',
                                  service_id='test',
                                  ssid='test',
                                  bssid='52:3e:aa:49:98:cb',
                                  server_name='test_server',
                                  proc_delay=9.0,
                                  request_size=100,
                                  e2e_delay=300.2)
        database.insert_obj(entry)
    assert database.session.query(db.EndUserService).count() == 201
    assert database.query_process_delay('test', 'test', 'test_server') == 9.0
    assert database.query_eu_data_size('test') == 100

def test_get_bw(database):
    for i in range(20):
        entry = db.NetworkRecord(timestamp=get_time(),
                                 src_node='source',
                                 dest_node='dest',
                                 latency=2*i,
                                 bw=i)
        database.insert_obj(entry)
    assert database.query_bw('source', 'dest') == 14.5
    assert database.query_bw('source', 'dest', size=20) == 9.5
    assert database.query_rtt('source', 'dest') == 29
    assert database.query_rtt('source', 'dest', size=20) == 19

def test_get_disk_size_and_get_capacities(database):
    entry = db.EdgeServerInfo(name='testsize', ip='127.0.0.2', distance=2,
                core_cpu=8, max_cpu=2e9, ram=10e9, disk=500e9)
    database.insert_obj(entry)
    assert database.query_server_size('testsize') == 500e9
    assert database.query_capacities('testsize') == 2e9

@pytest.mark.incremental
class TestDatabaseQuery(object):
    def test_clean_table(self,database):
        database.clean_database()
        assert database.session.query(db.MigrateRecord).count() == 0
        assert database.session.query(db.EndUserService).count() == 0
        assert database.session.query(db.EdgeServerInfo).count() == 0
        assert database.session.query(db.NetworkRecord).count() == 0

    def test_query_cur_assign(self, database):
        user_info = {'name':'testuser', 'bts':'test01', 'status':True}
        obj_user_info = db.EndUserInfo(name='testuser', bts='test01',
                                       service_id='test_test', status=True)
        obj_user_info.service = db.ServiceInfo(name='test_test',
                                       server_name='test_server',
                                       container_img='test_reg/test:latest',
                                       status='running', cpu=3e9,
                                       mem=5e9, size=1e9, no_request=0)
        database.insert_obj(obj_user_info)
        database.register_user(**user_info)
        assert database.query_cur_assign('testuser') ==\
            ('test01', 'test_server')
        database.update_cur_assign('testuser', 'test02', 'test01')
        assert database.query_cur_assign('testuser') == ('test02', 'test01')
        # rool back to correct association for further testing
        database.update_cur_assign('testuser', 'test01', 'test_server')
        assert database.query_cur_assign('testuser') ==\
            ('test01', 'test_server')

    def test_query_size_container(self,database):
        user = database.session.query(db.EndUserInfo).\
               filter(db.EndUserInfo.name == 'testuser').first()
        obj = user.service
        assert obj.method == 'delta' # Test default value
        assert obj.dump_dir == '/tmp'
        assert obj.user is not None
        obj = db.EndUserService(timestamp=get_time(), user_id='testuser',
                                service_id='test_test')
        database.insert_obj(obj)
        assert database.query_size_container('testuser') == 1e9

    def test_update_network_monitor(self, database):
        assert database.update_network_monitor_ip('10.99.99.99',
                                                  '10.99.99.100',
                                                  10.0, 100) == False
        obj = db.EdgeServerInfo(name='test_server',
            ip='10.99.99.99', distance=2,
            core_cpu=3, max_cpu=2e9, ram=2e9, disk=10e9, phi=1, rho=1)
        obj.bts_info = db.BTSInfo(name='Foo1')
        database.insert_obj(obj)
        obj = db.EdgeServerInfo(name='Foo2', ip='10.99.99.100', distance=2,
                core_cpu=3, max_cpu=2e9, ram=2e9, disk=10e9, phi=1, rho=1)
        obj.bts_info = db.BTSInfo(name='Foo2')
        database.insert_obj(obj)
        obj = db.EdgeServerInfo(name='FooCentre', ip='10.99.99.2', distance=0,
                core_cpu=12, max_cpu=3e9, ram=4e9, disk=40e9, phi=1, rho=1)
        database.insert_obj(obj)
        assert database.update_network_monitor_ip('10.99.99.99',
                                                  '10.99.99.100',
                                                  10.0, 100) == True
        assert database.update_network_monitor_ip('10.99.99.99',
                                                  '10.99.99.2',
                                                  7.0, 200) == True
        assert database.update_network_monitor_ip('10.99.99.100',
                                                  '10.99.99.2',
                                                  12.0, 150) == True
        assert database.update_network_monitor_ip('10.99.99.100',
                                                  '10.99.99.2',
                                                  12.0, 150) == True

    def test_get_rtt_bts_to_edge(self, database):
        assert database.query_bts_to_edge_rtt('Foo1', 'Foo2') == 10.0
        assert database.query_bts_to_edge_rtt('Foo1', 'FooCentre') ==7.0

    def test_query_bw(self, database):
        assert database.query_bw('test_server', 'Foo2') == 100
        assert database.query_bw('Foo2', 'FooCentre') == 150


    def test_update_container_monitor(self, database):
        container_monitor_msg = {'container': 'test_test',
                                 'status': 'running',
                                 'cpu': 0.1, # GHz
                                 'mem': 1e9, # MB
                                 'size': 1e9, # MB
                                 'delta_memory': 140, # B
                                 'pre_checkpoint': 500*10**6, # B
                                 'time_xdelta': 2.5, #s
                                 'time_checkpoint': 0.7 #s
                                 }
        database.update_container_monitor(plan=Constants.OPTIMIZED_PLAN,
            **container_monitor_msg)
        t_pre = database.get_est_pre_mig_time('testuser',
            'test_server', 'Foo2')
        assert t_pre > 0

    def test_update_eu_service_monitor(self, database):
        eu_service = {
            Constants.END_USER : 'test',
            Constants.SERVICE_NAME: 'openface',
            Constants.ASSOCIATED_SSID: 'edge02-bts',
            Constants.ASSOCIATED_BSSID:'52:3e:aa:49:98:cb',
            'startTime[ns]':3685422149965579,
            'endTime[ns]':3685422655153495,
            'processTime[ms]':301.27978515625,
            'sentSize[B]':5765}
        is_violate = database.update_eu_service_monitor(eu_service)
        assert is_violate is False

    def test_server_monitor(self, database):
        database.update_server_monitor('test_server', 2e9, 8, 16e9, 1e9, 100e9, 10e9)
        assert database.query_capacities('test_server') == 2e9

    def test_query_rho_and_phi(self, database):
        for i in range(20):
            obj = db.MigrateRecord(timestamp=get_time(), source='test_server',
                                   dest='Foo2', service='test_test',
                                   pre_checkpoint=1.0, pre_rsync=1.0,
                                   checkpoint=1.0, rsync=1.0,
                                   xdelta_source=1.0, final_rsync=1.0,
                                   restore=1.0, size_final_rsync=1e9,
                                   size_rsync=1e9)
            database.insert_obj(obj)
            database.update_phi('test_server')
        assert database.query_phi('test_server') == 16

    def test_get_service(self, database):
        s = database.get_service('testuser')
        assert s is not None
        assert s.name == 'test_test'

    def test_get_server(self, database):
        servers = database.get_server_names()
        print(servers)
        assert len(servers) > 0

    def test_get_server_with_distance(self, database):
        servers = database.get_server_names_with_distance(2)
        print(servers)
        assert len(servers) > 0

    def test_get_info_all_servers(self, database):
        all_servers = database.get_info_all_servers()
        print(all_servers)
        assert len(all_servers) > 0


    def test_update_rssi_monitor(self, database):
        btss = []
        r = 0
        x_src = 0
        x_dst = 70.0
        bts1 = 'test01'
        bts2 = 'Foo02'
        bts3 = 'Foo03'
        aps = [
            {'name':bts1, 'bssid':'51:3e:aa:49:98:cb',
            'passwd': '', 'x': x_src, 'y':r, 'server': 'docker1'},
            {'name':bts2, 'bssid':'51:3e:aa:49:98:cb',
            'passwd': '', 'x': x_dst, 'y':r, 'server': 'docker2'},
            {'name':bts3, 'bssid':'51:3e:aa:49:98:cc',
            'passwd': '', 'x': 40.0, 'y':50.0, 'server': 'docker3'}
            ]

        for ap in aps:
            database.register_bts(**ap)
            bts = BTSInfo(**ap)
            btss.append(bts)
        t = 0
        v = 1
        start = 20
        t_start = time.time()
        while t < 20:
            t_now = time.time()
            x = start + v*(t_now - t_start)
            y = 0
            print("user is at x={}, y={}".format(x, y))
            aps = generate_rssi_report(x,y,btss)
            database.update_rssi_monitor(user='testuser', aps=aps)
            t = t + 1
            time.sleep(0.90) # just for align with logic in central_database
            ts, erssi1 = database.query_last_eRSSIs('testuser', bts1)
            ts, erssi2 = database.query_last_eRSSIs('testuser', bts2)
            print("{}: erssi {}".format(bts2, erssi2))
            if t > 11:
                eta2, eta1, eta0 = database.query_rssi_predictor('testuser', bts1)
                est_rssi_foo1 = database.get_est_rssi_bts('testuser', bts1, 0)
                print("{}: eta2={}, eta1 ={}, eta0={}, est_rssi={}".
                    format(bts1, eta2, eta1, eta0, est_rssi_foo1))
                # check estimation
                assert abs(est_rssi_foo1 - erssi1[0]) < 5
                eta2, eta1, eta0 = database.query_rssi_predictor('testuser', bts2)
                est_rssi_foo2 = database.get_est_rssi_bts('testuser', bts2, 0)
                print("{}: eta2={}, eta1={}, eta0={}, est_rssi={}".
                    format(bts2, eta2, eta1, eta0, est_rssi_foo2))
                assert abs(est_rssi_foo2 - erssi2[0]) < 5
                till_ho = database.get_handover_time('testuser', bts1, bts2)
                print("till_ho[s] ={}".format(till_ho))
                theoretical = theorecal_handover(x, v, x_src, x_dst,
                                                   r)
                assert approx(till_ho, abs=6) == theoretical
        last_x, last_y = database.get_user_location('testuser')
        assert last_x == approx(40, abs=2)
        assert last_y == approx(0, abs=0.001)
        vx, vy = database.get_user_velocity('testuser')
        print('vx={},vy={}'.format(vx, vy))
        assert vx == approx(1, abs= 0.1)
        assert vy == approx(0, abs=0.001)

        bts = database.get_max_rssi_bts('testuser')
        assert bts.name == bts2
