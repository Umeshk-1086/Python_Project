import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/maanglo')
    DEBUG = True