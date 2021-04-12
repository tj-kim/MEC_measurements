from __future__ import division

import os
import sys
import math

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import wifi_spec

def log_rssi_model_int(d, n=3, A=30):
    # RSSI = -(10*n*log(d) + A), log base 10
    if d < 1:
        d = 1
    rssi = int(-(10*n*math.log10(d) + A))
    return rssi

def log_rssi_model_real(d, n=3, A=30):
    if d < 1:
        d = 1
    return -(10*n*math.log10(d) + A)

def handover_constant(env, bts, eu, default=0.5):
    return default # Handover 0.5s

def datarate_model(rssi):
    """Return the datarate at the given signal strength."""
    rssi_map = wifi_spec.RSSI_MAP_80211n_HT40_1_1_extend
    # Find a suitable map
    rate = next((e[1] for e in rssi_map[::-1] if e[0] < rssi),
                rssi_map[0][1])
    # (index, modulation name, datarate with GI 800ns,
    #    datarate with GI 400ns)
    return rate[-1]


def distance(rssi, n=3, A=-30):
    d = 10**((A-rssi)/(10*n))
    return d
