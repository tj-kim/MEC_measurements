import os
import sys
import logging

import sqlalchemy
from sqlalchemy import func
from sqlalchemy_utils import force_instant_defaults
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, ForeignKey

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utilities import get_time

Base = declarative_base()
force_instant_defaults()

class UserRequest(Base):
    __tablename__ = 'user_service'
    timestamp = Column(BigInteger, primary_key=True)
    user_id = Column(String)
    service_id = Column(String)
    ssid = Column(String)
    bssid = Column(String)
    server_name = Column(String)
    proc_delay = Column(Float) # unit ms
    e2e_delay = Column(Float) # ms
    request_size = Column(Integer) # unit B

class UserEvent(Base):
    __tablename__ = 'user_event'
    timestamp = Column(BigInteger, primary_key=True)
    user_id = Column(String)
    event_type = Column(String)
    data = Column(String)

class DBeu(object):
    def __init__(self, **kwargs):
        database = kwargs.get('database', 'simulated_eu.db')
        self.engine = sqlalchemy.create_engine('sqlite:///{}'.format(database))
        if not os.path.exists(database):
            logging.info("Create new database")
            Base.metadata.create_all(self.engine)
        else:
            Base.metadata.bind = self.engine
        self.DBSession = sessionmaker(bind=self.engine)
        self.session = self.DBSession()

    def get_all_request(self):
        return self.session.query(UserRequest)

    def update_service(self, **kwargs):
        obj = UserRequest(**kwargs)
        self.session.add(obj)

    def add_event(self, user, event_type, data):
        obj = UserEvent(timestamp=get_time(), user_id=user,
                        event_type=event_type, data=data)
        self.session.add(obj)

    def get_user_request_summary(self):
        """Shows the total request in the database

        This function shows a clearer information about the simulation
        results.

        Returns:
             The number of the requests.
        """
        results = self.session.query(func.count(UserRequest.timestamp)).all()
        return results

    def close(self):
        self.session.commit()
        self.session.close()
