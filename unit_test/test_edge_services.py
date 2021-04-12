from .. edge_services import EdgeServices
from .. migrate_node import MigrateNode
import yaml

def test_add_service():
    msg = '{"container_img": "ngovanmao/yolov3-mini-cpu-amd64:01", "end_user": "testdiscover", "ssid": "edge01", "bssid": "51:3e:aa:49:98:cb", "ip": "172.18.37.105", "container_port": 9988, "method": "delta", "snapshot": "snapshot", "registry": "ngovanmao", "dump_dir": "/tmp", "service_name": "yolo", "debug": true, "port": 9901, "user": "root"}'
    msg_json = yaml.safe_load(msg)
    service = MigrateNode(**msg_json)
    test_ip = "192.168.0.1"
    service.update_ip(test_ip)
    assert service.ip == test_ip
    services = EdgeServices()
    services.add_service(service)
    assert services.get_users_from_service(service.service_name)[0]\
        == service.end_user
    assert services.get_services_from_user(service.end_user)[0].ip\
        == test_ip
    assert services.get_service(service.end_user, service.service_name).ip\
        == test_ip

