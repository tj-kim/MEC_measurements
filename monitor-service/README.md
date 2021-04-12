In this folder, there are two ways to install prometheus and other services, 
e.g., node-exporter, cadvisor.
1. Install directly into the machine. Using script 1*.sh, and 2*.sh
2. Deploying services via Docker containers. If the normal edge node, 
we deploy node-exporter and cadvisor, while the edge node in tier1, 
we deploy a Prometheus server to scape the collecting metrics from 
the other services.

