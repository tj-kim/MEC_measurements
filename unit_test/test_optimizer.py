import pytest
from .. optimization_planner import OptimizationPlanner
from .. stats_edge import StatsEdge, StatsEdgeSql
from .. sql_service import Sqlite3NetworkMonitor
from .. discovery_edge import DiscoveryYaml
from .. planner import PlanResult
from .. central_database import EstimateTime
from .. import Constants

@pytest.mark.skip("Skip")
def test_optimizer():
    edge_nodes = DiscoveryYaml('real_edge_nodes.yml')
    netMon = Sqlite3NetworkMonitor(database='unit_test/testnetwork.db')
    m_stats = StatsEdge(edge_nodes, netMon)
    obj = OptimizationPlanner(stats=m_stats)
    next_assign = obj.compute_plan()
    print(next_assign)
    u1 = next(i for i in next_assign if i.user=='u1')
    u2 = next(i for i in next_assign if i.user=='u2')
    assert u1.next_bts == 'edge01'
    assert u1.next_server == 'edge01'
    assert u2.next_bts == 'edge02'
    assert u2.next_server == 'edge02'
# TODO: comment out later
@pytest.mark.skip("Skip")
def test_optimizer_sql(create_db):
    m_stats = StatsEdgeSql(database='unit_test/centraldb.db')
    m_stats.db.est_time_users['test'] = EstimateTime('test')
    container_info = {'container':'test_test',
        'status' : 'running',
        'cpu' : 10.01,
        'mem' : 1000,
        'size' : 200,
        'delta_memory': 12.3,
        'pre_checkpoint': 500*10**6, # B
        'time_xdelta': 2.5, #s
        'time_checkpoint': 0.7 #s
        }
    m_stats.db.update_container_monitor(plan=Constants.OPTIMIZED_PLAN,
        **container_info)
    monitor_msg_from_eu = {
        Constants.END_USER:'test',
        Constants.SERVICE_NAME:'test_test',
        Constants.ASSOCIATED_SSID:'docker1',
        Constants.ASSOCIATED_BSSID:'52:3e:aa:49:98:cb',
        'startTime[ns]':3685422149965579,
        'endTime[ns]':3685422655153495,
        "sentSize[B]":5765,
        'processTime[ms]':461.27978515625
        }
    m_stats.db.update_eu_service_monitor(monitor_msg_from_eu)
    obj = OptimizationPlanner(stats=m_stats)
    res = obj.place_service('test', 'test_test', 'docker1', '51:3e:aa:49:98:cb')
    assert res in ['centre', 'docker1', 'docker2', 'docker3']
    res = obj.compute_plan(0)
    # assert type(res[0])==PlanResult
