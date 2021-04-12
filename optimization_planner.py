import time
import random
import traceback
import logging
import itertools

import pulp

from planner import MigrationPlanner, PlanResult

class OptimizationPlanner(MigrationPlanner):
    def __init__(self, **kwargs):
        super(OptimizationPlanner, self).__init__(**kwargs)

    def diff_assign(self, cur_assign, next_assign):
        cur_dict = {}
        diffs = []
        for i in cur_assign.keys():
            # i <- (user, servers, bts)
            if cur_assign[i] != 0:
                cur_dict[i[0]]=(i[2], i[1])
        next_dict = {}
        for i in next_assign.keys():
            # i <- (user, servers, bts)
            if next_assign[i] != 0:
                next_dict[i[0]]=(i[2], i[1])
        for user in self.users:
            cur = cur_dict.get(user, None)
            new = next_dict.get(user, None)
            if cur != new:
                diffs.append(PlanResult(user, *next_dict[user]))
        return diffs

    def compute_plan(self, delta_time):
        self.users = self.stats.get_user_names()
        self.servers = self.stats.get_server_names()
        self.bss = self.stats.get_bts_names()
        self.cur_assign = {(u,s,b):self.stats.get_cur_assign(u,s,b)
                      for u,s,b in itertools.product(self.users,
                                                     self.servers,
                                                     self.bss)}
        if not self.stats.valid_info():
            logging.warn("Invalid information")
            return []
        # Check enough info
        no_connects = len(self.servers) - 1
        for u in self.users:
            if not self.stats.enough_info(u, no_connects):
                logging.warn("Not enough info for user {}".format(u))
                return []
        try:
            next_assign = self.solve(self.cur_assign, delta_time)
            return self.diff_assign(self.cur_assign, next_assign)
        except ZeroDivisionError:
            # When the planner cannot collect enough information, it raises
            # ZeroDivisionError.
            logging.error(traceback.format_exc())
            logging.error("Missing information")
            return []
        except TypeError:
            # When some parameters are not collected (proc_delay,..)
            logging.error(traceback.format_exc())
            logging.error("Lacking information")
            return []

    def solve(self, cur_assign, delta_time):
        start_time = time.time()
        m_stats = self.stats
        prob = pulp.LpProblem('AllocationEdge', pulp.LpMaximize)
        black_list = []
        black_list_users = []
        for u in self.users:
            neighbors = m_stats.get_estimated_neighbor(u, delta_time)
            if len(neighbors) == 0:
                black_list_users.append(u)
                continue
            for b,s in itertools.product(self.bss, self.servers):
                if b not in neighbors:
                    # prob += assign_vars[(u,s,b)] == 0
                    black_list.append((u,s,b))

        self.users = [i for i in self.users if i not in black_list_users]
        assign_vars = pulp.LpVariable.dicts("Associated",
            list(itertools.product(self.users,
                                   self.servers,
                                   self.bss)),
            0, 1, pulp.LpBinary)

        logging.debug("Current assign: {}".format(self.cur_assign))
        logging.debug("Calculation:\n{}".format("\n".join([
            "{},{},{}->{},{}".format(*variables) for variables in \
            itertools.product(self.servers, self.bss, self.users,
                              self.servers, self.bss) \
            if cur_assign[variables[2], variables[0], variables[1]]!=0 and \
            (variables[2], variables[3], variables[4]) not in black_list
        ])))
        object_function = lambda s, b, u, next_s, next_b: \
            (m_stats.get_delta_delay(u, s, next_s, b, next_b, delta_time) \
             *m_stats.get_est_number_request(u, next_s, next_b)\
             - m_stats.get_downtime(u, s, next_s, b, next_b))\
             * cur_assign[u,s,b] \
             * assign_vars[(u, next_s, next_b)]

        prob += pulp.lpSum([ object_function(*variables) for variables in \
                            itertools.product(self.servers, self.bss, self.users,
                                              self.servers, self.bss) \
        if self.cur_assign[variables[2], variables[0], variables[1]]!=0 and \
            (variables[2], variables[3], variables[4]) not in black_list])

        # Constraint 1: user k associates with only 1 self.bss, and 1 server
        for u in self.users:
            prob += pulp.lpSum(
                [assign_vars[(u,s,b)]
                 for s,b in itertools.product(self.servers, self.bss)]) == 1

        # Constraint 2: the resource (CPU) used for user k is available at the
        # server i.
        for s in self.servers:
            prob += pulp.lpSum([
                assign_vars[(u,s,b)]*m_stats.get_average_cpu_container(u)
                for u,b in itertools.product(self.users, self.bss)]) \
                    <= m_stats.get_full_capacities(s)

        # Constraint 3: the resource (RAM) used for user k is available at the
        # server i
        for s in self.servers:
            prob += pulp.lpSum([
                assign_vars[(u,s,b)]*m_stats.get_memory_container(u)
                for u, b in itertools.product(self.users, self.bss)]) \
                    <= m_stats.get_memory_server(s)

        # Constraint 4: the resource (Disk) used for user k is available at the
        # server i
        for s in self.servers:
            prob += pulp.lpSum([
                assign_vars[(u,s,b)]*m_stats.get_size_container(u)
                for u, b in itertools.product(self.users, self.bss)]) \
                    <= m_stats.get_size_server(s)

        # Constraint 5: only care the neighboring self.bss.
        for u, s, b in itertools.product(self.users, self.servers, self.bss):
            if (u, s, b) in black_list:
                prob += assign_vars[(u,s,b)] == 0

        # Constraint 6: maximum number of associating EUs
        # base station b
        for b in self.bss:
            prob += pulp.lpSum([
                assign_vars[(u,s,b)]
                for u, s in itertools.product(self.users, self.servers)])\
                    <= m_stats.get_max_assoc_users(b)

        logging.info("solving problem...{}".format(prob))
        prob.solve()
        logging.info("status {}".format(pulp.LpStatus[prob.status]))
        self.assign_next = {}
        for v in itertools.product(self.users, self.servers, self.bss):
            self.assign_next[v] = assign_vars[v].varValue
            if assign_vars[v].varValue > 0.0001:
                logging.info("assign User-Server-BS {}".format(v))
        """
        for variable in prob.variables():
            print("{} = {}".format(variable.name, variable.varValue))
            if variable.varValue > 0:
                print("Assign users {}".format(variable.varValue))
        """
        logging.info("optimal profit value ={}".format(pulp.value(prob.objective)))
        logging.info("New assign values = {}".format(self.assign_next))
        logging.info("Calculation time = {}".format(time.time() - start_time))
        if pulp.LpStatus[prob.status] != 'Optimal':
            self.assign_next = self.cur_assign
        return self.assign_next

    def place_service(self, user, service, ssid, bssid):
        # Deploy in the cloud server
        #distance = 0
        #cloud_server = self.stats.get_a_server_with_distance(distance)
        #logging.debug('Deploy to {}'.format(cloud_server))
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
