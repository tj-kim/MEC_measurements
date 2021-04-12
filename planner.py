import random
import logging
from collections import namedtuple
from central_database import get_time
import Constants

PlanResult = namedtuple('PlanResult', ['user', 'next_bts', 'next_server'])

class MigrationPlanner(object):
    def __init__(self, **kwargs):
        self.mode = kwargs.get('mode', 'random')
        self.elapsed_time = kwargs.get('elapsed_time', 3)
        self.stats = kwargs.get('stats')
        self.cur_assign = {}
        self.next_assign = {}

    def get_plan(self, user):
        assign = self.cur_assign.get(user, None)
        return PlanResult(user, *assign) if assign is not None else None

    def place_service(self):
        raise NotImplementedError

    def lifetime_to_average_pre_mig(self, end_user):
        life_time = 1000 # seconds, which is long enough
        self.cur_assign[end_user] = self.stats.db.query_cur_assign(end_user)
        if self.cur_assign[end_user] is None:
            logging.error("Cannot found current server or bts for user {}".\
                          format(end_user))
            return None, None
        (cur_bts, cur_server) = self.cur_assign[end_user]
        # Get average T_preMig from current server to any destination
        T_pre_mig_avg = self.stats.db.query_avg_t_pre_mig(end_user) # in s
        if T_pre_mig_avg is None:
            logging.error("query too soon, or service is deadth")
            return None, None
        last_time = 10*10**6 # 10s
        neighbor_bts = self.stats.db.query_neighbor(end_user, last_time)
        T_ho = 0.5
        for d in neighbor_bts:
            d_bts = d.bts
            if d_bts == cur_bts:
                continue
            hysteresis = 2.0 # dBm
            till_ho = self.stats.db.get_handover_time(end_user, cur_bts, d_bts,
                                                      hysteresis)
            # elapsed time till handover is real timestamp in second
            if till_ho is None:
                continue
            temp_time = till_ho - 1.1 * T_pre_mig_avg # in s
            logging.debug("till_ho={} T_pre_mig_avg={} temp time = {}".format(
                till_ho, T_pre_mig_avg, temp_time))
            if temp_time < life_time:
                life_time = temp_time
        return T_pre_mig_avg, life_time # in s

    def lifetime_to_max_pre_mig(self, end_user):
        life_time = 1000 # seconds, which is long enough
        self.cur_assign[end_user] = self.stats.db.query_cur_assign(end_user)
        if self.cur_assign[end_user] is None:
            logging.error("Cannot found current server or bts for user {}".\
                          format(end_user))
            return None, None
        (cur_bts, cur_server) = self.cur_assign[end_user]
        # Get maximum T_preMig from current server to any destination
        T_pre_mig_max = self.stats.db.query_max_t_pre_mig(end_user) # in s
        if T_pre_mig_max is None:
            logging.error("query too soon, or service is deadth")
            return None, None
        last_time = 10*10**6 # 10s
        neighbor_bts = self.stats.db.query_neighbor(end_user, last_time)
        T_ho = 0.5
        for d in neighbor_bts:
            d_bts = d.bts
            if d_bts == cur_bts:
                continue
            hysteresis = 2.0 # dBm
            till_ho = self.stats.db.get_handover_time(end_user, cur_bts, d_bts,
                                                      hysteresis)
            # elapsed time till handover is real timestamp in second
            if till_ho is None:
                continue
            temp_time = till_ho - 1.1 * T_pre_mig_max # in s
            logging.debug("till_ho={} T_pre_mig_max={} temp time = {}".format(
                till_ho, T_pre_mig_max, temp_time))
            if temp_time < life_time:
                life_time = temp_time
        return T_pre_mig_max, life_time # in s

    def lifetime_to_pre_mig(self, end_user, dest_server, dest_bts):
        life_time = 1000
        self.cur_assign[end_user] = self.stats.db.query_cur_assign(end_user)
        if self.cur_assign[end_user] is None:
            logging.error("Cannot found current server or bts for user {}".\
                          format(end_user))
            return life_time
        (cur_bts, cur_server) = self.cur_assign[end_user]
        if cur_server == dest_server:
            T_mig = 0
            T_pre_mig = 0
        else:
            T_pre_mig = self.stats.db.get_est_pre_mig_time(end_user, cur_server,
                dest_server)
            T_mig = self.stats.db.get_est_mig_time(end_user, cur_server,
                dest_server)
        if T_mig is None or T_pre_mig is None:
            logging.error("Too early ask for lifetime to mig.")
            return None
        if cur_bts == dest_bts:
            T_ho = 0
            life_time = 0 # force to mig immediately
        else:
            T_ho = self.stats.db.get_est_handover_time(end_user, cur_bts,
                dest_bts)
            till_ho = self.stats.db.get_handover_time(end_user, cur_bts,
                dest_bts) # till_ho is in second
            if till_ho is None:
                return None
            temp_time = till_ho - 1.1 * (max(T_ho, T_mig) + T_pre_mig)
            logging.debug("u/db/ds=[{}/{}/{}] till_ho={},T_pre_mig={}, T_mig={},temp_time = {}".
                format(end_user, dest_bts, dest_server,
                    till_ho, T_pre_mig, T_mig, temp_time))
            if temp_time < life_time:
                life_time = temp_time
        return life_time # in s

    def lifetime_to_mig(self, end_user, dest_server, dest_bts):
        life_time = 1000
        self.cur_assign[end_user] = self.stats.db.query_cur_assign(end_user)
        if self.cur_assign[end_user] is None:
            logging.error("Cannot found current server or bts for user {}".\
                          format(end_user))
            return life_time
        (cur_bts, cur_server) = self.cur_assign[end_user]
        if cur_server == dest_server:
            T_mig = 0
        else:
            T_mig = self.stats.db.get_est_mig_time(end_user, cur_server,
                dest_server)
        if T_mig is None:
            logging.error("Too early ask for lifetime to mig.")
            return None
        if cur_bts == dest_bts:
            T_ho = 0
            life_time = 0 # force to mig immediately
        else:
            T_ho = self.stats.db.get_est_handover_time(end_user, cur_bts,
                dest_bts)
            till_ho = self.stats.db.get_handover_time(end_user, cur_bts,
                dest_bts) # till_ho is in second
            if till_ho is None:
                return None
            temp_time = till_ho - 1.1 * max(T_ho, T_mig)
            if temp_time < life_time:
                life_time = temp_time
            logging.debug("TIME_TO_MIG u/db/ds=[{}/{}/{}] T_mig={}, till_ho={}, time_to_mig = {}".
                format(end_user, dest_bts, dest_server,
                    T_mig, till_ho, life_time))
        return life_time # in s

class CloudPlanner(MigrationPlanner):
    def __init__(self, **kwargs):
        super(CloudPlanner, self).__init__(**kwargs)

    def compute_plan(self, delta_time = 0):
        users = self.stats.get_user_names()
        distance = 0
        cloud_server = self.stats.get_a_server_with_distance(distance)
        diffs = []
        logging.debug("Cloud server {}".format(cloud_server))
        logging.debug("Users {}".format(users))
        for user in users:
            self.cur_assign[user] = self.stats.get_usr_assign(user)
            bts = self.stats.get_max_rssi_threshold_bts(user)
            if bts is None:
                continue
            last_assign = self.cur_assign.get(user, None)
            logging.debug("User {} switch to bts {} from {}".\
                          format(user, bts.name, last_assign))
            if last_assign[0] != bts.name:
                diffs.append(PlanResult(user, bts.name, cloud_server))
        return diffs

    def place_service(self, user, service, ssid, bssid):
        # Deploy in the cloud server
        distance = 0
        cloud_server = self.stats.get_a_server_with_distance(distance)
        logging.debug("Deploy to {}".format(cloud_server))
        return cloud_server

class RandomPlanner(MigrationPlanner):
    def __init__(self,  **kwargs):
        super(RandomPlanner, self).__init__(**kwargs)

    def compute_plan(self, delta_time = 0):
        users = self.stats.get_user_names()
        servers = self.stats.get_server_names()
        diffs = []
        for user in users:
            self.cur_assign[user] = self.stats.get_usr_assign(user)
            # select strongest BTS if the current is lower than threshold
            bts = self.stats.get_max_rssi_threshold_bts(user)
            if bts is None:
                continue
            bts_ssid = bts.name
            last_assign = self.cur_assign.get(user, None)
            if last_assign is None:
                continue
            if bts_ssid != last_assign[0]:
                # Server is randomly chosen
                new_server_name = random.choice(servers)
                new_assign = (bts_ssid, new_server_name)
                self.next_assign[user] = new_assign
                diffs.append(PlanResult(user, *new_assign))
        return diffs

    def place_service(self, user, service, ssid, bssid):
        servers = self.stats.get_server_names()
        return random.choice(self.stats.get_server_names())

class RSSIPlanner(MigrationPlanner):
    """This is a simple planner, which selects the best AP if the current rssi
    small than a predefined threshold.

    :mode: - random: choose random next server
           - first fit: choose a first fit available resource server
           - optimal: choose based on the return of optimizer function
    """
    def __init__(self, **kwargs):
        super(RSSIPlanner, self).__init__(**kwargs)

    def compute_plan(self, delta_time = 0):
        users = self.stats.get_user_names()
        servers = self.stats.get_server_names()
        diffs = []
        for user in users:
            self.cur_assign[user] = self.stats.get_usr_assign(user)
            bts = self.stats.get_max_rssi_bts(user)
            if bts is None:
                # Cannot find enough information to allocate this user
                continue
            # Stay in the same AP if it doesn't have edge server
            if bts.server_id is not None:
                if bts.server.core_cpu == 0:
                    new_assign = (bts.name, self.cur_assign[user][1])
                else:
                    new_assign = (bts.name, bts.server_id)
            else:
                new_assign = (bts.name, self.cur_assign[user][1])
            last_assign = self.cur_assign.get(user, None)
            self.cur_assign[user] = new_assign
            if last_assign != new_assign:
                diffs.append(PlanResult(user, *new_assign))
        return diffs

    def place_service(self, user, service, ssid, bssid):
        """First deployment of a service.

        Find the server that associate with the AP. Otherwise, pick a
        random server.

        """
        servers = self.stats.get_server_names()
        bts = self.stats.get_bts(ssid, bssid)
        if bts is None:
            # TODO: it should be deploy in cloud, for now, return random
            return random.choice(servers)
        if bts.server_id is None:
            return random.choice(servers)
        elif bts.server.core_cpu == 0:
            return random.choice(servers)
        else:
            return bts.server_id
