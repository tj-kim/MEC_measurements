
class EdgeServices(object):
    def __init__(self):
        self.services = []
        self.users = []

    def add_service(self, service):
        #service = MigrateNode(service)
        self.services.append(service)
        user_name = service.end_user
        if not self.is_associated_user(user_name):
            self.users.append(user_name)

    def find_index_service(self, service):
        service_name = service.service_name
        user_name = service.end_user
        return next((s[0] for s in enumerate(self.services)
            if s[1].service_name == service_name and s[1].end_user == user_name),
            None)

    def remove_service(self, service):
        i = self.find_index_service(service)
        if i is not None:
            del(self.services[i])

    def update_service(self, service):
        i = self.find_index_service(service)
        if i is not None:
            self.services[i] = service
        else:
            self.add_service(service)

    def is_associated_user(self, user_name):
        return user_name in self.users

    def get_users_from_service(self, service_name):
        return [ s.end_user for s in self.services
            if s.service_name == service_name ]

    def get_services_from_user(self, user_name):
        return [ s for s in self.services
            if s.end_user == user_name ]

    def get_service(self, user_name, service_name):
        return next((s for s in self.services
            if s.service_name == service_name and s.end_user == user_name),
            None)

    def get_services_with_server(self, server_name):
        return [ s for s in self.services
            if s.server_name == server_name ]

    def get_containers(self):
        return [(s.get_container_name(), s.get_container_img())
                for s in self.services]
