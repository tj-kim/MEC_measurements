import random

class EdgeServers(object):
    def __init__(self):
        self.servers = []

    def add_new_server(self, server_info):
        """
        {"server_name":edge01,"ip":172.18.37.105,"bs":edge01}
        """
        if self.find_index_server(server_info) is None:
            self.servers.append(server_info)

    def find_index_server(self, server_info):
        target_name = server_info['server_name']
        return next((s[0] for s in enumerate(self.servers)
            if s[1]['server_name'] == target_name), None)

    def remove_server(self, server_info):
        i = self.find_index_server(server_info)
        if i is not None:
            del(self.servers[i])

    def get_server_info(self, server_name):
        return next((s for s in self.servers
            if s['server_name'] == server_name), None)

    def get_ip_servers(self):
        return [ s['ip'] for s in self.servers]

    def get_name_servers(self):
        return [ s['server_name'] for s in self.servers]

    def get_ip_associated_server(self, bs):
        return next((s['ip'] for s in self.servers
            if s['bs'] == bs), None)

    def get_ip_random_server(self):
        i = random.choice(range(len(self.servers)))
        return self.servers[i]['ip']

    def get_name_associated_server(self, bs):
        return next((s['server_name'] for s in self.servers
            if s['bs'] == bs), None)

    def get_name_random_server(self):
        i = random.choice(range(len(self.servers)))
        return self.servers[i]['server_name']

    def get_server_name_from_ip(self, ip):
        return next((s['server_name'] for s in self.servers
            if s['ip'] == ip), None)

    def update_server(self, server_info):
        idx = self.find_index_server(server_info)
        if idx is None:
            self.servers.append(server_info)
        else:
            self.servers[idx] = server_info


    def update_my_neighbors(self, my_info, all_servers):
        is_registered = False
        for s in all_servers:
            if s['server_name'] != my_info['server_name']:
                self.update_server(s)
            else:
                is_registered = True
        return is_registered

