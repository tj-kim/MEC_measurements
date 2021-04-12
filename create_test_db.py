import time
import os
import json

import discovery_edge
import central_database as db

def get_time():
    return int(time.time()*1000000)

PATH = 'unit_test/centraldb.db'

def init_all_edge_servers(db_handle, edge_nodes):
    # Insert centre server information
    centre = edge_nodes.centre[0]
    print('centre = {}'.format(centre))
    obj = db.EdgeServerInfo(name=centre['name'], ip=centre['ip'])
    db_handle.insert_obj(obj)

    # Init all edge servers
    for ap in edge_nodes.servers:
        obj = db.EdgeServerInfo(name=ap['name'], ip=ap['ip'], core_cpu=1,
                                max_cpu=3e9, ram=8192, ram_free=4096, disk=20,
                                disk_free=10, distance=ap['distance'],
                                phi=0.02, rho=0.09)
        db_handle.insert_obj(obj)
    for ap in edge_nodes.aps:
        obj = db.BTSInfo(name=ap['name'], server_id=ap['server'],
                bssid=ap['bssid'], pwd=ap['passwd'])
        db_handle.insert_obj(obj)

def init_service_profiles(db_handle):
    # Init service profiles
    services = [{'name': 'ngovanmao/openface:12', 'avg_dproc':300, 'avg_len':26008},
                {'name': 'ngovanmao/yolov3-mini-cpu-amd64:01', 'avg_dproc':3000,
                 'avg_len':26008},
                {'name': 'test_reg/test:latest', 'avg_dproc':10, 'avg_len':100}]
    for s in services:
        obj = db.ServiceProfile(**s)
        db_handle.insert_obj(obj)

def init_end_user(db_handle, edge_nodes):
    # Init end user
    users = edge_nodes.get_end_users()
    ap = edge_nodes.aps[0]
    server_name = edge_nodes.servers[0]['name']
    for user in users:
        obj = db.EndUserInfo(name=user['name'], bts=edge_nodes.aps[0]['name'],
                         status=True, velocity=5.0)
        obj.service = db.ServiceInfo(name='{}_test'.format(user['name']),
                        container_img='test_reg/test:latest', port=9901,
                        server_name=server_name, status='running', cpu=0.1,
                        mem=100, size=1, delta_memory=100,
                        pre_checkpoint=1400, no_request=0)
        db_handle.insert_obj(obj)
        obj = db.EndUserService(timestamp=get_time(), user_id=user['name'],
                                service_id='test_test', ssid=ap['name'],
                                server_name=server_name,
                                bssid=ap['bssid'],
                                proc_delay=10, request_size=100)
        db_handle.insert_obj(obj)

def init_network(db_handle, edge_nodes):
    # Init network
    for i in range(20):
        for ap in edge_nodes.servers:
            for m in ap['metrics']:
                obj = db.NetworkRecord(timestamp=get_time(), src_node=ap['name'],
                                   dest_node=m['name'], latency=m['delay'], bw=m['bw'])
                db_handle.insert_obj(obj)

def init_rssi(db_handle, edge_nodes):
    # Init test RSSI
    RSSI_TABLE = {
        ('test', 'edge01'):-56,
        ('test', 'edge02'):-90,
        ('test', 'edge03'):-100}
    for i in range(20):
        for ap in edge_nodes.aps:
            rssi = RSSI_TABLE[('test', ap['name'])]
            obj = db.RSSIMonitor(timestamp=get_time(), user_id='test',
                             bts=ap['name'],
                             rssi=rssi,
                             erssi=rssi)
            db_handle.insert_obj(obj)

def main():
    edge_nodes = discovery_edge.DiscoveryYaml('edge_nodes.yml')
    if os.path.exists(PATH):
        os.remove(PATH)
    db_handle = db.DBCentral(database=PATH)
    init_all_edge_servers(db_handle, edge_nodes)
    init_service_profiles(db_handle)
    init_end_user(db_handle, edge_nodes)
    init_network(db_handle, edge_nodes)
    init_rssi(db_handle, edge_nodes)
    db_handle.close()
