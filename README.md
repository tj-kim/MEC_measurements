# Introduction
This project is to design an edge computing system that jointly supports handover
and container migration for mobile end-users.
The edge computing system consists of three main components: 
* Central-controller: collects statistic information of edge servers, base stations, 
and mobile users, then based on this information to make a decision of migration
and/or base-station (BS) handover for each mobile user.

* Edge servers (and collocated base stations): 
  * deploys, monitors offloaded services (which are 
Docker containers) for offloading heavily computational tasks (e.g., image processing),
  * monitors its availablity and usage resources (compute, disk, network, memory).
  * *Cloud server*: is a logical edge server located in cloud, which is far away
  from mobile users.

* Mobile users (MUs): leverage powerful edge servers for offloading tasks
(i.e., image processing), provide some statistic information to the central-controller
(e.g., end-to-end delay to indicate its quality of services). 

<span style="color:blue">**For more details, please read our paper:** [Globecom'20] Mao V. Ngo, Tie Luo, Hieu T. Hoang, and Tony Q.S. Quek, "Coordinated Container Migration and Base Station Handover in Mobile Edge Computing," IEEE Global Communications Conference (GLOBECOM), December 2020.</span>  [PDF](https://arxiv.org/abs/2009.05682), [Video](https://youtu.be/IqsHe43lHaw)

# Software modules:
## Central-controller: 
* **Central database**: stores all statistics infomation, and historical data of users.
* **Monitor**: is an entry point for collecting data
* **Planner**: combine all data to make a decision of handover-migration. 
* **Deployment**: issue an intruction for edge server to deploy offloaded edge services.
`centralized_controller.py` is a main file for central-controller.

## Edge servers:
* **Migration service**: handles migration a running offloaded service 
from source edge server to destination edge server.
* **Deployment-S service**: cooperate with central-controller to deploy Docker container
for mobiler users in an edge server.
* **Resource monitoring service**: monitor the current edge server's resource (CPU, RAM, network I/O usage and availability)
* **Discovery service**: automatically discover a new nearby edge server if they are joining into the networks. 
`edge_controller.py` is a main file for edge server.

### Offloaded services:
We have built three stateful offloaded services:
* Face recognition: is based on an opensource implementation [Openface](http://cmusatyalab.github.io/openface/). 
The Docker container is: ```ngovanmao/openface:17```.
Demo of real-time face detection using Docker container of Openface service is available at: https://youtu.be/EI-nAs_SC3g


* Object recognition: is based on well-known implementation [YoloV3](https://pjreddie.com/darknet/yolo/). 
But we use [YoloV3 with CPU implementation based on OpenCV](https://www.learnopencv.com/deep-learning-based-object-detection-using-yolov3-with-opencv-python-c/).
The Docker container is ```ngovanmao/u1404_opencv_py3_yolov3:05```

* Simple service: is a dumb TCP server that simply responds to each incoming offloading 
request with an incrementing counter (and hence the processing delay is treated as zero).
The Docker container is ```gochit/simple_tcp_service:03```. Code of simple service is in 
```docker_test_service```

In order to simulate stateful applications, all the three offloaded services store 
and increment counter after each incoming offloading request. The counter is checked 
before and after migration to ensure consistent state of each offloaded service.

Implementation of the two image processing offloaded services: https://gitlab.com/ngovanmao/edgeapps

## Mobile users:
### Virtual mobile users:
To get reproducible result, we implement virtual mobile users: inside end-user folder.

### Android mobile user: 
We implemented the android version here: https://gitlab.com/ngovanmao/edgecamar


There are a folder /docker-yolo containing a script and Dockerfile to build Yolo service container in 
CPU/GPU with amd64 and arm64v8 architectures.

Here is a demo of Android app that offloads computationally intensive tasks (object recognition based on Yolo-v3, and face recognition based on Openface)
to a running Docker container (offloaded edge services) on edge servers:
* Demo of object recognition Android app with a Docker container--offloaded services running on Jetson edge server (layer-2 of hierarchcial edge computing): https://youtu.be/6FETIIdDqe8
* Demo of face recognition Android app with a Docker container--offloaded services running on DevBox cloud server: https://youtu.be/7AzQ88y7K1M

# How to install MEC system:
## Centrol-controller:
To setup central-controller, just run the `setup_centre.sh` script which deploys a `centre_edge` service on central-controller server.
We can start central controller in a central-controller server, or in the cloud server. Monitor, restart the service with following command:
```
sudo service centre_edge status
sudo service centre_edge restart
```

## Edge server:
To setup edge server, just run the script `setup_edgenode.sh` which deploys
`migrate` service is for running edge server modules (the name `migrate` is an inherent history issue :) ).

Our edge server is collocated with a WiFi AP which is setup with WiFi dongle (TP-LAC1200 T4U).
To setup WiFi-AP, just run a setup script in `setup-ap` folder.

To monitor the `migrate` service, we can use the following commands:
```
sudo service migrate status
sudo service migrate start/restart/stop
```

For virtual base-station that does not collocate with a "real" edge server, we simulate it as a Null server.
Run `setup_nat.sh` to make base-station as a router.
Setup NAT for edge servers to simulate router's function.
```
cd /opt/edge/
sudo ./setup_nat.sh start eno1
```
You can change the interface `eno1` to the interface that is using in edge servers.

## Simulated mobile users:
https://gitlab.com/ngovanmao/edgecomputing/wikis/Setup-Routing-packets-for-a-simulated-MU

# Citation
Please cite EdgeComputing in your publications if it helps your research:
```
@proceeding{MaoGlobecom2020,
  title="{Coordinated Container Migration and Base Station Handover in Mobile Edge Computing}",
  author={Mao~V.~Ngo and Tie~Luo and Hieu~T.~Hoang and Tony~Q.~S.~Quek},
  booktitle={Proc. IEEE GLOBECOM},
  pages={},
  year={2020},
  month ={Dec.},
  address = {Taiwan}
}
```
# References:
* Opensource solver CBC from COIN-OR: https://projects.coin-or.org/Cbc (accessed Apr. 15, 2019)
* CRIU, checkpoint and restore in user space: https://criu.org (accessed Apr. 12, 2019)
* 802.11n + 802.11ac date rates and SNR requirements: https://higher-frequency.blogpost.com (accessed Sep. 24, 2018).

------
Please look at the wiki for more details, and contact us if you have any questions during replicating the system.
If any bug, please create an issue.

