import time
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from cryptography.fernet import Fernet

Base = declarative_base()
engine = create_engine('sqlite:///example.db')
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    password = Column(String)

Base.metadata.create_all(engine)

def redact_sensitive_info(data):
    if isinstance(data, dict):
        redacted = {k: redact_sensitive_info(v) for k, v in data.items()}
        if 'password' in redacted:
            redacted['password'] = 'REDACTED'
        return redacted
    return data

def audit_function(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        logging.info(f"Function {func.__name__} executed in {end_time - start_time} seconds")
        return result
    return wrapper

@contextmanager
def secure_context():
    key = Fernet.generate_key()
    cipher_suite = Fernet(key)
    try:
        yield cipher_suite
    finally:
        del key

@audit_function
def insert_user(name, password):
    session = Session()
    user = User(name=name, password=password)
    session.add(user)
    session.commit()
    session.close()
    return user

@audit_function
def get_user(user_id):
    session = Session()
    user = session.query(User).filter_by(id=user_id).first()
    session.close()
    return user

@audit_function
def update_user(user_id, name, password):
    session = Session()
    user = session.query(User).filter_by(id=user_id).first()
    user.name = name
    user.password = password
    session.commit()
    session.close()
    return user

@audit_function
def delete_user(user_id):
    session = Session()
    user = session.query(User).filter_by(id=user_id).first()
    session.delete(user)
    session.commit()
    session.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with secure_context() as cipher_suite:
        encrypted_password = cipher_suite.encrypt(b'sensitive_password')
        insert_user('john_doe', encrypted_password.decode())
        user = get_user(1)
        print(redact_sensitive_info(user.__dict__))
        update_user(1, 'john_doe_updated', cipher_suite.encrypt(b'new_sensitive_password').decode())
        user = get_user(1)
        print(redact_sensitive_info(user.__dict__))
        delete_user(1)