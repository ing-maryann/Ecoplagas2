import psycopg2
from psycopg2.extras import RealDictCursor
from config import config

class Database:
    def __init__(self):
        self.connection = None
        self.connect()
        self.create_table()

    def connect(self):
        try:
            self.connection = psycopg2.connect(config.DATABASE_URL)
            print("✅ Conexión a PostgreSQL exitosa")
        except Exception as error:
            print(f"❌ Error conectando a PostgreSQL: {error}")

    def create_table(self):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS usuarios (
                        id SERIAL PRIMARY KEY,
                        nombre VARCHAR(100) NOT NULL,
                        correo VARCHAR(255) UNIQUE NOT NULL,
                        contrasena_hash VARCHAR(255) NOT NULL,
                        fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                self.connection.commit()
                print("✅ Tabla 'usuarios' verificada/creada exitosamente")
        except Exception as error:
            print(f"❌ Error creando tabla: {error}")

    def execute_query(self, query, params=None):
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if query.strip().upper().startswith('SELECT'):
                    return cursor.fetchall()
                else:
                    self.connection.commit()
                    return cursor.rowcount
        except Exception as error:
            self.connection.rollback()
            print(f"❌ Error ejecutando query: {error}")
            raise error

    def close(self):
        if self.connection:
            self.connection.close()
            print("🔌 Conexión a PostgreSQL cerrada")