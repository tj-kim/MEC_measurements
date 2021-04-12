from __future__ import division

import os
import time

import mock
import pytest
import sqlalchemy

from .. import planner
from .. import discovery_edge
from .. import Constants
from .. import stats_edge
from .. import central_database as db

DATABASE_NAME = 'unit-test-planner.db'

@pytest.fixture(scope='module')
def database():
    if os.path.isfile(DATABASE_NAME):
        os.remove(DATABASE_NAME)
    d = db.DBCentral(database=DATABASE_NAME)
    # Prepare servers
    d.register_server(name='docker1', ip='10.0.99.10', bs='edge01')
    d.register_server(name='docker2', ip='10.0.99.11', bs='edge02')
    d.register_server(name='docker3', ip='10.0.99.12', bs='edge03')
    d.register_user(name='test', bts='edge02')
    yield d
    d.close()

@pytest.fixture(scope='module')
def edgestats(database):
    stats = stats_edge.StatsEdgeSql(database=DATABASE_NAME)
    return stats

def test_rssi_planner(edgestats, database):
    """This test case uses monitor data in the database. To change this test case,
    you need to change data in the database too.
    """
    obj = planner.RSSIPlanner(stats=edgestats)
    res = obj.place_service('test', 'test_test', 'edge02', '51:3e:aa:49:98:cb')
    assert res == 'docker2'
    # Edit user
    user = database.session.query(db.EndUserInfo).\
           filter(db.EndUserInfo.name=='test').first()
    user.service = db.ServiceInfo(name='test_test', server_name='docker2')
    rssi = db.RSSIMonitor(timestamp=db.get_time(), user_id='test', bts='edge01',
                          rssi=-62)
    database.insert_obj(rssi)
    rssi = db.RSSIMonitor(timestamp=db.get_time(), user_id='test', bts='edge02',
                          rssi=-60)
    database.insert_obj(rssi)
    rssi = db.RSSIMonitor(timestamp=db.get_time(), user_id='test', bts='edge03',
                          rssi=-58)
    database.insert_obj(rssi)
    database.session.commit()
    res = obj.compute_plan()[0]
    assert res.next_server == 'docker3'
    assert res.next_bts == 'edge03'

def test_random_planner(edgestats):
    obj = planner.RandomPlanner(stats=edgestats)
    res = obj.place_service('test', 'test_test', 'docker1', '51:3e:aa:49:98:cb')
    assert res in ['docker1', 'docker2', 'docker3']
    res = obj.compute_plan()
    print(res)
    for i in res:
        assert i.next_server in ['docker1', 'docker2', 'docker3']
        assert i.next_bts in ['edge01', 'edge02', 'edge03']

def test_rssi_to_bw():
    assert 150 == stats_edge.wifi_rssi_to_bw(-30)
