This folder contains Vagrant file for dummy nodes deployment. Use the 
following command to deploy the nodes:

    vagrant up --provision
    
You should change the username and password in `wpa_supplicant.conf`
into a correct one and make sure the interface name in the last
provision line is correct.

