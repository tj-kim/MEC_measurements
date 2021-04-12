#!/usr/bin/env python
import argparse
import math

import estimator

class GeneralPlacement(object):
    def __init__(self, **kwargs):
        self.number_bs = kwargs.get('number_bs', 1)
        self.distance_bs = kwargs.get('distance_bs', 70) #m

    def get_position_bs(self):
        raise NotImplementedError

    def get_distance_2bs(self, source_id, dest_id):
        (x_s, y_s) = self.coords[source_id]
        (x_d, y_d) = self.coords[dest_id]
        return estimator.euclidean_distance((x_s, y_s),
                                            (x_d, y_d))

class LinearPlacement(GeneralPlacement):
    def __init__(self, **kwargs):
        super(LinearPlacement, self).__init__(**kwargs)
        self.coords = {}

    def get_position_bs(self):
        for i in range(self.number_bs):
            x = self.distance_bs*i
            y = 0
            self.coords[i] = (x, y)
            print("BS-{} at x={}, y={}".format(i, x, y))
        return self.coords

class CirclePlacement(GeneralPlacement):
    def __init__(self, **kwargs):
        super(CirclePlacement, self).__init__(**kwargs)
        self.angle = 2.0*math.pi/self.number_bs
        self.radius = self.distance_bs/math.sqrt( 2 - 2 * math.cos(self.angle) )

    def get_radius(self):
        print("radius={}".format(self.radius))
        return self.radius

    def get_position_bs(self):
        self.coords = {}
        for i in range(self.number_bs):
            x = self.radius*math.cos(self.angle*i)
            y = self.radius*math.sin(self.angle*i)
            self.coords[i] = (x, y)
            print("BS-{} at x={}, y={}".format(i, x, y))
        return self.coords

