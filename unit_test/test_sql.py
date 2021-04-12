import os
from subprocess import check_output

import mock

from .. sql_service import *
from .. utilities import get_hostname


def test_sql_service():
    database = '{}networkTest.db'.format(get_hostname())
    if os.path.isfile(database):
        check_output(['savelog', '-ntl', database])
    table = 'networkMetric'
    sqlService = Sqlite3Service(database=database, table=table)
    columns = 'timestamp text, source_dest text, latency real, bandwidth real'
    sqlService.create_table(columns)
    value1 = "'2018-06-07 174502', '172.18.35.104_172.18.33.123', 123.0, 938.2"
    sqlService.insert_data(value1)
    read_all_data = sqlService.read_all_data()
    print("check {} = {}".format(read_all_data[0][3], float(value1.split(',')[3])))
    assert read_all_data[0][3] == float(value1.split(',')[3])
    # Test conditional read data
    value2 = "'2018-06-07 174602', '172.18.35.104_172.18.33.123', 223.0, 938.2"
    sqlService.insert_data(value2)
    read_data = sqlService.read_conditional_data("latency > 150")
    print("check {} = {}".format(read_data[0][3], float(value2.split(',')[3])))
    assert read_data[0][3] == float(value2.split(',')[3])
    sqlService.close_connection()

def test_sql_net_metric():
    sqlNet = Sqlite3NetworkMonitor()
    sqlNet.create()
    tss = ['20180726224325', '20180726232607']
    source_ip = '172.18.35.104'
    dest_ip = '172.18.33.123'
    latencies = [123.0, 130.1]
    bandwidths = [938.2, 899.1]
    for i, ts in enumerate(tss):
        sqlNet.insert_net_metrics(ts, source_ip, dest_ip, latencies[i], bandwidths[i])
    read_all_data = sqlNet.read_all_data()
    print("all data={}".format(read_all_data))
    print("check {} = {}".format(read_all_data[0][2], latencies[0]))
    assert read_all_data[0][2] == latencies[0]
    last_bw = sqlNet.get_last_bw(source_ip, dest_ip)
    print("last_bw: {}={}".format(last_bw, bandwidths[1]))
    assert last_bw == bandwidths[1]
    last_delay = sqlNet.get_last_delay(source_ip, dest_ip)
    print("last_delay: {}=={}".format(last_delay, latencies[1]))
    assert last_delay == latencies[1]
    last_delay_bw = sqlNet.get_last_delay_bw(source_ip, dest_ip)
    print("last delay_bw: {}==({}, {})".format(last_delay_bw, latencies[1], bandwidths[1]))
    assert last_delay_bw == (latencies[1], bandwidths[1])
    sqlNet.close_connection()

def test_read_sql_net_metric():
    source_ip = '172.18.35.104'
    dest_ip = '172.18.33.123'
    latencies = [123.0, 130.1]
    bandwidths = [938.2, 899.1]
    sqlNet = Sqlite3NetworkMonitor()
    read_all_data = sqlNet.read_all_data()
    print("all data={}".format(read_all_data))
    print("check {} = {}".format(read_all_data[0][2], latencies[0]))
    assert read_all_data[0][2] == latencies[0]
    last_bw = sqlNet.get_last_bw(source_ip, dest_ip)
    print("last_bw: {}={}".format(last_bw, bandwidths[1]))
    assert last_bw == bandwidths[1]
    last_delay = sqlNet.get_last_delay(source_ip, dest_ip)
    print("last_delay: {}=={}".format(last_delay, latencies[1]))
    assert last_delay == latencies[1]
    last_delay_bw = sqlNet.get_last_delay_bw(source_ip, dest_ip)
    print("last delay_bw: {}==({}, {})".format(last_delay_bw, latencies[1], bandwidths[1]))
    assert last_delay_bw == (latencies[1], bandwidths[1])
    sqlNet.close_connection()

def test_sql_container_metric():
    sqlContainer = Sqlite3ContainerMonitor()
    sqlContainer.create()
    data = ('2018-06-07 174502', 'foo', 'running', 0.1, 100, 1000)
    sqlContainer.insert_container_metrics(*data)
    read_all_data = sqlContainer.read_all_data()
    # Compare all data
    assert read_all_data[0] == data

def test_sql_server_metric():
    sqlServer = Sqlite3ServerMonitor()
    sqlServer.create()
    data = ('2018-06-07 174502', 3600, 8, 16348, 2394, 700, 564)
    sqlServer.insert_server_metrics(*data)
    read_all_data = sqlServer.read_all_data()
    assert read_all_data[0] == data
