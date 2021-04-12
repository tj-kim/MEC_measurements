#!/bin/bash
sudo apt update
sudo apt install -y git dkms
#git clone  https://github.com/ptpt52/rtl8812au.git ~/Downloads/rtl8812au
#cd ~/Downloads/rtl8812au
git clone https://github.com/abperiasamy/rtl8812AU_8821AU_linux.git ~/Downloads/rtl8812AU_8821AU_linux
cd ~/Downloads/rtl8812AU_8821AU_linux
sudo make -f Makefile.dkms install
sudo modprobe rtl8812au
