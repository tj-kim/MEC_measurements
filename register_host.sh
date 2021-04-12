#!/bin/bash

echo "" > /root/.ssh/known_hosts
ssh-keyscan -H 10.0.99.9 >> /root/.ssh/known_hosts
ssh-keyscan -H 10.0.99.10 >> /root/.ssh/known_hosts
ssh-keyscan -H 10.0.99.11 >> /root/.ssh/known_hosts
ssh-keyscan -H 10.0.99.12 >> /root/.ssh/known_hosts
