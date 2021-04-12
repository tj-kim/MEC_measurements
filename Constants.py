PORT = "port"
MIGRATION = "migration"
NEXT_SSID = "nextSSID"
NEXT_BSSID = "nextBSSID"
NEXT_PASSWORD = "nextPassword"
ELAPSED_TIME = "elapsedTime"
NEXT_EDGE_IP = "nextEdgeIP"
NEXT_EDGE_PORT = "nextEdgePort"

SSID = "SSID"
BSSID = "BSSID"
NEARBY_AP = "nearbyAP"
RSSI = "level"
CHANNEL_MODE = "ChannelMode"
FREQUENCY = "frequency"

# keyword for controller msg
UPDATED_SERVERS = 'updated'
REGISTER = "register"
MONITOR = "monitor"
MONITOR_ALL = "monitor/#"
MONITOR_EDGE = "monitor/edge"
MONITOR_EDGE_ALL = "monitor/edge/+"
MONITOR_SERVER = "monitor/server"
MONITOR_SERVER_ALL = "monitor/server/+"
MONITOR_CONTAINER = "monitor/container"
MONITOR_CONTAINER_ALL = "monitor/container/+"
MONITOR_EU = "monitor/eu"
MONITOR_EU_ALL = "monitor/eu/+"
MONITOR_SERVICE = 'monitor/service'
MONITOR_SERVICE_ALL = 'monitor/service/+'
MIGRATE_REPORT = 'migrate_report'
MIGRATE_REPORT_ALL = 'migrate_report/+/+'
DISCOVER = "discover"
DEPLOY = "deploy"
PRE_MIGRATE = 'pre_migrate'
MIGRATE = 'migrate'
PRE_MIGRATED = 'pre_migrated'
PRE_MIGRATED_ALL = 'pre_migrated/+'
MIGRATED = 'migrated'
MIGRATED_ALL = 'migrated/+'
HANDOVER = 'handover'
HANDOVERED = 'handovered'
HANDOVERED_ALL = 'handovered/+'
ALLOCATED = 'allocated'
ALLOCATED_ALL = 'allocated/+'
DESTROY = "destroy"
LWT = "LWT"
LWT_ALL = "LWT/+/+"
LWT_CENTRE='LWT/centre'
LWT_EDGE = "LWT/edge"
LWT_EDGE_ALL = "LWT/edge/+"
LWT_EU = "LWT/eu"
LWT_EU_ALL = "LWT/eu/+"


ASSOCIATED = "associated"
ASSOCIATED_SSID = "ssid"
ASSOCIATED_BSSID = "bssid"
SERVICE = "service"
SERVICE_NAME = "service_name"
SERVICE_IP = "serviceIP"
SERVICE_PORT = "servicePort"
SERVER_NAME = "server_name"

END_USER = "end_user"
OPENFACE = "openface"
YOLO = "yolo"
SIMPLE_SERVICE = "simple"
OPENFACE_DOCKER_IMAGE = "ngovanmao/openface:17"
YOLO_DOCKER_IMAGE = "ngovanmao/u1404_opencv_py3_yolov3:05"
YOLO_MINI_DOCKER_IMAGE = "ngovanmao/yolov3-mini-cpu-amd64:01"
SIMPLE_DOCKER_IMAGE = "gochit/simple_tcp_service:03"

BETWEEN_EDGES_PORT = 5678
BROKER_PORT        = 9999

MIGRATE_METHOD = "migrate_method"
NON_LIVE_MIGRATION = "non_live_migration"
PRE_COPY = "pre_copy"
POST_COPY = "post_copy"

RSSI_THRESHOLD = -76
RSSI_MINIMUM = -83
# handover: relative RSSI hysteresis with predicted RSSI values
# migration based on optmization
OPTIMIZED_PLAN = 'optimization'
# Handover based on RSSI threshold (-76 dBm)
# Migration to the nearest server argmax(bw + 1/latency)
NEAREST_PLAN   = 'nearest'
# Handover based on RSSI threshold (-76 dBm)
# Migration to a random server
RANDOM_PLAN    = 'random'
# Service always on the cloud server
CLOUD_PLAN = 'cloud'
