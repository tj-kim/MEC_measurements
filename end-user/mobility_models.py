from __future__ import division

import math
import time
import logging

class SimpleRoundTripMoving(object):
    def __init__(self, **kwargs):
        """
        Moving from (start_x, y) to (stop_x, y) and go back
        """
        self.velocity = kwargs.get('velocity', 0)
        self.wait_time = kwargs.get('wait_time', 0)
        self.start_x = kwargs.get('start_x', 0)
        self.stop_x = kwargs.get('stop_x', 0)
        self.y = kwargs.get('y', 0)
        self.length = abs(self.stop_x - self.start_x)
        self.direction = 1 if self.start_x < self.stop_x else -1
        self.lower_bound = min(self.stop_x, self.start_x)
        self.upper_bound = max(self.stop_x, self.start_x)
        self.start_time = time.time() + self.wait_time

    def start_moving(self):
        self.last_time = time.time()
        self.start_time = time.time() + self.wait_time
        self.current_x = self.start_x

    def get_new_position(self):
        new_time = time.time()
        delta_time = new_time - self.last_time
        if self.last_time < self.start_time:
            delta_time -= (self.start_time - self.last_time)
        if delta_time < 0:
            self.last_time = new_time
            return self.current_x, self.y
        if self.length != 0:
            distance = delta_time*self.velocity
            rounds = distance//(2*self.length)
            remain = distance%(2*self.length)
            new_x = self.current_x + remain*self.direction
            if new_x > self.upper_bound:
                new_x = self.upper_bound - (new_x - self.upper_bound)
                self.direction *= -1
                logging.info("A user reached its stop point, turn back!")
            elif new_x < self.lower_bound:
                new_x = self.lower_bound + (self.lower_bound - new_x)
                self.direction *= -1
                logging.info("A user reached its start point, turn back!")
            new_y = self.y
            self.current_x = new_x
        else:
            new_x = self.current_x
            new_y = self.y
        self.last_time = new_time
        return new_x, new_y

class CircleTripMoving(object):
    """ The circle trip moving model to simulate the mobility around a center point (0,0)
    with radius R, and velocity v, start from position (R, 0) and move with anti-clockwise
    direction.
    """
    def __init__(self, **kwargs):
        # direction = 1 is for anti-clockwise, -1 is for clockwise
        self.direction = kwargs.get('direction', 1)
        self.velocity = kwargs.get('velocity', 0)
        self.wait_time = kwargs.get('wait_time', 0)
        self.start_x = kwargs.get('start_x', 0)
        self.start_y = kwargs.get('start_y', 0)
        self.radius = kwargs.get('radius')

    def start_moving(self):
        self.start_time = time.time() + self.wait_time
        self.current_x = self.start_x
        self.current_y = self.start_y

    def get_new_position(self):
        time_now = time.time()
        elapsed_time = time_now - self.start_time
        if time_now < self.start_time:
            return self.current_x, self.current_y
        angle = self.direction * (elapsed_time * self.velocity /self.radius)
        self.current_x = self.radius * math.cos(angle)
        self.current_y = self.radius * math.sin(angle)
        return self.current_x, self.current_y
