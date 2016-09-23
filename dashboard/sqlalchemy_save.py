from datetime import datetime
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    name = Column(String(20), nullable=False)
    timezone = 
    update_time = Column(DateTime, default=datetime.utcnow())
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    active = Column(Bool)
    schedule_interval_sec = Column(Int)
    operator = Column(String) # bash, python, sql, etc
    cmd = Column(String) 

    def __repr__(self):
        return "<Job(name={}, active={})>".format(self.name, self.active)


Base.metadata.create_all()

Session = sessionmaker(bind=engine)
session = Session()

job1 = Job(name='sleep', start)