from __future__ import division

import numpy as np
import sympy
import logging

from utilities import approx

def euclidean_distance(a, b):
    x_a, y_a = a
    x_b, y_b = b
    return np.sqrt((x_a - x_b)**2 + (y_a - y_b)**2)

def find_hand_over_coeffs():
    x_src, y_src = sympy.symbols('x_src y_src')
    x_dst, y_dst = sympy.symbols('x_dst y_dst')
    x, y = sympy.symbols('x y')
    a, b = sympy.symbols('a b')
    omega = sympy.symbols('omega')

    d2_src = (x-x_src)**2 + (y-y_src)**2
    d2_dst = (x-x_dst)**2 + (y-y_dst)**2
    eq = d2_src - omega*d2_dst
    # Replacing y = a*x + b
    subs_expr = eq.subs(y, a*x + b)
    # Expanding the expression
    expand_expr = sympy.expand(subs_expr)
    # Convert to polynomial form
    poly = expand_expr.as_poly(x)
    return [ sympy.lambdify((a,b,x_src,y_src,x_dst, y_dst, omega), coeff)
             for coeff in  poly.all_coeffs() ]
    
handover_coeffs = find_hand_over_coeffs()

def find_handover_points(a, b, src, dst, hys=7.0, n=3, A=-30):
    """Finds where to handover.

    Link: https://gitlab.com/ngovanmao/edgecomputing/wikis/Estimate-distance-from-the-end-user-to-the-base-station
    
    Returns:
        Handover points. Return `None` if the user will not handover.
    """

    omega = 10**(hys/(5*n))
    x_src, y_src = src
    x_dst, y_dst = dst
    coeffs = [ coeff(a, b, x_src, y_src, x_dst, y_dst, omega)
               for coeff in handover_coeffs ]
    roots = np.roots(coeffs)
    logging.debug("The equation {} has roots:{}".format(coeff,
                                                        roots))
    if not all(np.isreal(roots)):
        logging.debug("Cannot found any real solution")
        return None
    return [(x, a*x+b) for x in roots]

def find_remain_time(pos, target, velocity, eps=0.00001):
    """Finds the time to travel to a target point.

    Args:
        pos (tuple): the current position in meters (x, y)
        target (tuple): the target position in meters (x, y)
        velocity (tuple): the current velocity in m/s (v_x, v_y)
        eps (float): tolerance for comparison, default is 0.00001.

    Returns:
        Remain times in seconds.

    Raises:
        ValueError: when the user cannot reach to the point.
    """

    v_x, v_y = velocity
    x_dst, y_dst = target
    x_cur, y_cur = pos
    t_x = None
    t_y = None
    if not approx(v_x, 0, eps):
        t_x = (x_dst - x_cur) / v_x
    if not approx(v_y, 0, eps):
        t_y = (y_dst - y_cur) / v_y
    if t_x is None and approx(x_dst, x_cur, eps):
        return t_y
    elif t_y is None and approx(y_dst, y_cur, eps):
        return t_x
    elif t_x == t_y:
        return t_x
    else:
        raise ValueError("Invalid target point: {} != {}.".format(t_x, t_y))

def estimate_new_position(pos, velocity, time):
    """Estimates the new position of the user in `time` seconds.

    Args:
        pos (tuple): the current position in m (x, y).
        velocity (tuple): the current velocity in m/s (v_x, v_y).
        time (float): estimate time in seconds.

    Returns:
        The estimated position (x_new, y_new).
    """
    x, y = pos
    v_x, v_y = velocity
    return (x + v_x*time, y + v_y*time)
