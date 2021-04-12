import random
import logging
import collections

import Constants
import central_database as cdb
from wifi_spec import RSSI_MAP_80211n_HT40_1_1_extend

s_request = {'u1':1000, 'u2':2000, 'u3':3000}
rssi = {('u1','edge01'):-56,('u1','edge02'):-90,('u1','edge03'):-100,
    ('u2','edge01'):-92,('u2','edge02'):-53,('u2','edge03'):-100}
v = {'u1':5.0, 'u2':6.0} # mps
rssi_thresh = -67 # dBm


def wifi_rssi_to_bw(rssi):
    for spec in RSSI_MAP_80211n_HT40_1_1_extend[::-1]:
        if spec[0] < rssi:
            return spec[1].dr_400ns
    return RSSI_MAP_80211n_HT40_1_1_extend[0][1].dr_400ns

class StatsEdge(object):
    def __init__(self, edge_nodes, netMonitor):
        self.t_checkpoints = []
        self.size_container = 0
        self.edge_nodes = edge_nodes
        self.server_names = self.edge_nodes.get_server_names()
        self.server_ips = self.edge_nodes.get_ips()
        self.netMonitor = netMonitor
        # CPU capacity
        self.capacities = {'edge01':2.7e9, 'edge02':2.9e9, 'edge03':3.5e9} # GHz
        # current assignment (k,i,j):
        self.cur_assign = {
            'u1': ('edge02', 'edge02'),
            'u2': ('edge03', 'edge03')
        }
        self.num_users = 2
        self.num_servers = 3
        self.num_bs = 3

    def get_cur_assign(self, u, s, b):
        assign = self.cur_assign[u]
        return 1 if assign[0]==s and assign[1]==b else 0

    def get_usr_assign(self, u):
        return self.cur_assign[u]

    def get_RTT(self, s, next_s):
        if s == next_s:
            return 0
        ip_s = self.edge_nodes.get_server_ip(s)
        ip_next_s = self.edge_nodes.get_server_ip(next_s)
        rtt_s_next_s = self.netMonitor.get_last_delay(ip_s, ip_next_s)
        #print("RTT {}_{} = {}".format(i, next_i, rtt_i_next_i))
        return rtt_s_next_s

    def add_new_user(self):
        self.num_users += 1

    def remove_user(self):
        self.num_users -= 1

    def get_bw(self, u, b, s, delta_time):
        # in Mbps
        return min(self.get_access_bw(u, b, delta_time),
            self.get_edge_bw(b, s, delta_time))

    def get_access_bw(self, u, s):
        return 54 # Mbps

    def get_edge_bw(self, s, next_s):
        if s == next_s:
            return 10e9
        else:
            ip_s = self.edge_nodes.get_server_ip(s)
            ip_next_s = self.edge_nodes.get_server_ip(next_s)
            bw_s_next_s = self.netMonitor.get_last_bw(ip_s, ip_next_s)
            #print("bandwidth {}_{} = {}".format(i, next_i, bw_i_next_i))
            return bw_s_next_s

    def get_size_server(self, s):
        S_servers = {'edge01': 250e9,'edge02':150e9,'edge03':200e9} # MB
        return S_servers[s]

    def get_size_container(self, service_u):
        S_containers = {'u1':150e6, 'u2':2000e6, 'u3':345e6}
        return S_containers[service_u]

    """
    ====================== Cost of migration==========================
    Estimate Migration time and downtime service
    """
    def get_phi(self, s):
        # get average t_checkpoint[k][i]*capacities[i] * x[(k,i)]/S_containers[k]
        phi = {'edge01':0.01, 'edge02':0.02, 'edge03':0.05}
        return phi[s]

    def get_rho(self, s):
        rho = {'edge01':0.01, 'edge02':0.02, 'edge03':0.05}
        return rho[s]

    def get_estimate_t_checkpoint(self, u, s):
        return self.get_phi(s) * self.get_size_container(u) / self.capacities[s]

    def get_estimate_t_transfer(self, u, s, next_s):
        return self.get_size_container(u) / self.get_edge_bw(s, next_s)

    def get_estimate_t_restore(self, u, next_s):
        return self.get_rho(next_s) * self.get_size_container(u) / self.capacities[next_s]

    def get_estimate_t_migration(self, u, s, next_s):
        t_checkpoint = self.get_estimate_t_checkpoint(u, s)
        t_transfer = self.get_estimate_t_transfer(u, s, next_s)
        t_restore = self.get_estimate_t_restore(u, next_s)
        return (t_checkpoint + t_transfer + t_restore)

    def update_t_checkpoint(self, t_checkpoint):
        self.t_checkpoints.append(t_checkpoint)

    def update_process_delay(self, u, s, delay):
        self.proc_delays[(u, s)] = delay

    def get_process_delay(self, u, b, s):
        # service k, server i
        proc_delays = {('u1','edge01', 'edge01'): 0.9, ('u1','edge01', 'edge02'): 0.9,
            ('u1','edge01', 'edge03'): 0.9,
            ('u1','edge02', 'edge01'):1.0, ('u1','edge02', 'edge02'):1.0, ('u1','edge02', 'edge03'):1.0,
            ('u1','edge03', 'edge01'): 1.0, ('u1','edge03', 'edge02'): 1.0, ('u1','edge03', 'edge03'): 1.0,
            ('u2','edge01', 'edge01'): 0.8, ('u2','edge01', 'edge02'): 0.8, ('u2','edge01', 'edge03'): 0.8,
            ('u2','edge02', 'edge01'):0.7, ('u2','edge02', 'edge02'):0.7, ('u2','edge02', 'edge03'):0.7,
            ('u2','edge03', 'edge01'):0.89, ('u2','edge03', 'edge02'):0.89, ('u2','edge03', 'edge03'):0.89 }
        return proc_delays[(u, s)]

    def get_delta_delay(self, u, s, next_s, b, next_b, delta_time):
        if s == next_s and b == next_b:
            return 0
        delta_delay = self.get_process_delay(u, b, s) * \
            (1 - self.capacities[s]/self.capacities[next_s])\
            + s_request[u] * ((1/self.get_bw(u,b,s) - 1/self.get_bw(u,next_b, next_s))\
            + (self.get_RTT(s, b) - self.get_RTT(next_s, next_b)))
        return delta_delay

    def get_downtime(self, u, s, next_s, b, next_b):
        if s == next_s:
            return 0
        else:
            return self.get_estimate_t_migration(u, s, next_s)

    def get_server_names(self):
        return ['edge01', 'edge02', 'edge03']

    def get_bts_names(self):
        return ['edge01','edge02', 'edge03']

    def get_user_names(self):
        return ['u1', 'u2']

class StatsEdgeSql(StatsEdge):
    """A version of stats_edge.StatsEdge, which uses the central SQL database
    instead of fake data.
    """
    def __init__(self, db_control=None, **kwargs):
        if db_control is not None:
            self.db = db_control
        else:
            self.db = cdb.DBCentral(**kwargs)

    def get_cur_assign(self, u, s, b):
        usr_assign = self.db.query_cur_assign(u)
        return 1 if usr_assign[0] == b and usr_assign[1] == s else 0

    def get_usr_assign(self, u):
        return self.db.query_cur_assign(u)

    def get_RTT(self, s, next_s):
        if s == next_s:
            return 0
        return self.db.query_rtt(s, next_s)

    def get_bts_edge_RTT(self, b, s):
        rtt = self.db.query_bts_to_edge_rtt(b, s)
        logging.debug("RTT {} - {} [microsec]:{}".format(b,s,rtt))
        return rtt

    def get_bw(self, u, b, s, delta_time):
        bw = min(self.get_access_bw(u, b, delta_time),
            self.get_bts_to_edge_bw(b, s))
        logging.debug("Delta={}. BW[Mbps] ubs [{}-{}-{}]={}".
            format(delta_time, u, b, s, bw))
        return bw

    def get_s_request(self, user):
        return self.db.query_eu_data_size(user)

    def get_full_capacities(self, server_name):
        return self.db.query_full_capacities(server_name)

    def get_capacities(self, name):
        return self.db.query_capacities(name)

    def get_access_bw(self, u, b, delta_time):
        #timeout = 7*10**6 # microsecond
        erssi = self.db.get_est_rssi_bts(u, b, delta_time)
        if rssi is None:
            return 0
        else:
            bw = wifi_rssi_to_bw(erssi)
            logging.debug("Access BW eRSSI={}, delta={}, u-b[{}-{}]={}".
                format(erssi, delta_time, u, b, bw))
            return bw

    def get_edge_bw(self, s, next_s):
        if s == next_s:
            return 10e9
        else:
            return self.db.query_bw(s, next_s)

    def get_bts_to_edge_bw(self, b, next_s):
        """Queries BW from BTS to edge server.

        .. note::
            This approach assumes that the BTS always link with a edge server.
        """
        return self.db.query_bts_to_edge_bw(b, next_s)

    def get_size_server(self, s):
        return self.db.query_server_size(s)

    def get_memory_server(self, s):
        return self.db.query_server_memory(s)

    def get_average_cpu_container(self, end_user):
        ret = self.db.query_average_cpu_container(end_user)
        return ret

    def get_size_container(self, service_u):
        ret =  self.db.query_size_container(service_u)
        return ret

    def get_memory_container(self, service_u):
        ret =  self.db.query_memory_container(service_u)
        return ret

    def get_neighbor(self, u):
        timeout = 5*10**6 # last 5 seconds
        ret = self.db.query_neighbor(u, timeout)
        return [ i.bts for i in ret if i.rssi > Constants.RSSI_MINIMUM ]

    def get_estimated_neighbor(self, u, time):
        return self.db.query_neighbor_candidates(u,
                                            Constants.RSSI_MINIMUM,
                                            time)

    """
    ====================== Cost of migration==========================
    Estimate Migration time and downtime service
    """
    def get_phi(self, i):
        return self.db.query_phi(i)

    def get_rho(self, i):
        return self.db.query_rho(i)

    def get_process_delay(self, u, b, s):
        # service for user u, BTS b, server s
        return self.db.query_process_delay(u, b, s)

    def get_delta_delay(self, u, s, next_s, b, next_b, delta_time):
        if s == next_s and b == next_b:
            return 0
        # current we design app use multiple threads/cores
        cur_cap = self.get_full_capacities(s) # in MHz
        next_cap = self.get_full_capacities(next_s) # in MHz
        cur_bw = self.get_bw(u,b,s,delta_time) # in Mbps
        next_bw = self.get_bw(u,next_b, next_s, delta_time) # in Mbps
        cur_rtt = self.get_bts_edge_RTT(b, s) # in microsecond
        next_rtt = self.get_bts_edge_RTT(next_b, next_s) # in microsecond

        # process_delay is in millisecond
        old_proc_delay = self.get_process_delay(u, b, s)
        if old_proc_delay is None:
            return None
        process_delay = old_proc_delay *(1 - cur_cap/next_cap)

        # self.get_s_request(u) is in byte = 8 bits
        # prop_delay is in microsecond
        prop_delay = self.get_s_request(u)* 8 *\
                     (1/cur_bw-1/next_bw) + (cur_rtt-next_rtt)
        delta_delay = prop_delay + process_delay * 10.0**3
        logging.debug("Est after {} Delta delay [us] {}-[{}-{}][{}-{}]= {}us + {}ms = {}".
            format(delta_time, u, b, next_b, s, next_s, prop_delay,
                process_delay, delta_delay))
        # delta_delay is in microsecond
        return delta_delay

    def get_est_number_request(self, u, next_s, next_b):
        # assume n_request(next_s, next_b) = n_request(u)
        ret = self.db.query_number_request(u)
        logging.debug("Number est request user {}={}".format(u, ret))
        return ret


    def get_downtime(self, u, s, next_s, b, next_b):
        T_ho = self.db.get_est_handover_time(u, b, next_b)
        T_mig = self.db.get_est_mig_time(u, s, next_s) # in second
        if T_mig is None:
            return None
        else:
            DT = max(T_mig, T_ho) * 10**6 # convert s to us
            logging.debug("Downtime[us] {}-[{}-{}][{}-{}]={}".format(
                u, b, next_b, s, next_s, DT))
            return DT

    def get_max_assoc_users(self, b):
        max_assoc_users = 200 # each BS serves max 200 mobile EUs
        return max_assoc_users

    def get_server_names(self):
        return self.db.get_server_names()

    def get_bts_names(self):
        return self.db.get_bts_names()

    def get_user_names(self):
        return self.db.get_user_names()

    def get_max_rssi_threshold_bts(self, user):
        return self.db.get_max_rssi_threshold_bts(user)

    def get_max_rssi_bts(self, user):
        return self.db.get_max_rssi_bts(user)

    def get_bts(self, name, bssid):
        return self.db.get_bts_info(name, bssid)

    def valid_info(self):
        return self.db.valid_info()

    def enough_info(self, user, no_connects):
        if self.db.est_time_users[user].no_connect < no_connects:
            logging.debug("user {} has {} connects < {}".format(user,
                self.db.est_time_users[user].no_connect, no_connects))
            return False
        return True

    def get_a_server_with_distance(self, distance):
        servers = self.db.get_server_names_with_distance(distance)
        print("servers ...{}".format(servers))
        if len(servers) > 0:
            return random.choice(servers)
        else:
            return None
