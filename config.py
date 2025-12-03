import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'Ecoplagas')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '310503')
    
    @property
    def DATABASE_URL(self):
        return f"postgresql://{self.DB_postgres}:{self.DB_310503}@{self.DB_localhost}:{self.DB_5432}/{self.DB_Ecoplagas}"


config = Config()
