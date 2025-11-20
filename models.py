from database import Database
from werkzeug.security import generate_password_hash, check_password_hash
import re

class Usuario:
    def __init__(self):
        self.db = Database()

    def validar_correo(self, correo):
        """Valida el formato del correo electrónico"""
        patron = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(patron, correo) is not None

    def crear_usuario(self, nombre, correo, contrasena):
        """Crea un nuevo usuario en la base de datos"""
        try:
            # Validaciones
            if not nombre or not correo or not contrasena:
                return False, "Todos los campos son obligatorios"
            
            if not self.validar_correo(correo):
                return False, "Formato de correo electrónico inválido"
            
            if len(contrasena) < 6:
                return False, "La contraseña debe tener al menos 6 caracteres"

            # Hash de la contraseña
            contrasena_hash = generate_password_hash(contrasena)

            # Insertar en la base de datos
            query = """
                INSERT INTO usuarios (nombre, correo, contrasena_hash)
                VALUES (%s, %s, %s)
                RETURNING id, nombre, correo, fecha_creacion;
            """
            resultado = self.db.execute_query(query, (nombre, correo, contrasena_hash))
            
            if resultado:
                usuario_creado = resultado[0]
                return True, {
                    'id': usuario_creado['id'],
                    'nombre': usuario_creado['nombre'],
                    'correo': usuario_creado['correo'],
                    'fecha_creacion': usuario_creado['fecha_creacion']
                }
            else:
                return False, "Error al crear el usuario"

        except Exception as e:
            if "duplicate key value" in str(e):
                return False, "El correo electrónico ya está registrado"
            return False, f"Error del sistema: {str(e)}"

    def verificar_usuario(self, correo, contrasena):
        """Verifica las credenciales del usuario"""
        try:
            query = "SELECT * FROM usuarios WHERE correo = %s;"
            resultado = self.db.execute_query(query, (correo,))
            
            if not resultado:
                return False, "Usuario no encontrado"
            
            usuario = resultado[0]
            
            if check_password_hash(usuario['contrasena_hash'], contrasena):
                return True, {
                    'id': usuario['id'],
                    'nombre': usuario['nombre'],
                    'correo': usuario['correo']
                }
            else:
                return False, "Contraseña incorrecta"

        except Exception as e:
            return False, f"Error del sistema: {str(e)}"

    def obtener_usuario_por_id(self, usuario_id):
        """Obtiene un usuario por su ID"""
        try:
            query = "SELECT id, nombre, correo, fecha_creacion FROM usuarios WHERE id = %s;"
            resultado = self.db.execute_query(query, (usuario_id,))
            
            if resultado:
                return True, resultado[0]
            else:
                return False, "Usuario no encontrado"

        except Exception as e:
            return False, f"Error del sistema: {str(e)}"

    def obtener_todos_los_usuarios(self):
        """Obtiene todos los usuarios (para administración)"""
        try:
            query = "SELECT id, nombre, correo, fecha_creacion FROM usuarios ORDER BY fecha_creacion DESC;"
            resultado = self.db.execute_query(query)
            return True, resultado

        except Exception as e:
            return False, f"Error del sistema: {str(e)}"

    def actualizar_usuario(self, usuario_id, nombre=None, correo=None, contrasena=None):
        """Actualiza la información del usuario"""
        try:
            updates = []
            params = []
            
            if nombre:
                updates.append("nombre = %s")
                params.append(nombre)
            
            if correo:
                if not self.validar_correo(correo):
                    return False, "Formato de correo electrónico inválido"
                updates.append("correo = %s")
                params.append(correo)
            
            if contrasena:
                if len(contrasena) < 6:
                    return False, "La contraseña debe tener al menos 6 caracteres"
                contrasena_hash = generate_password_hash(contrasena)
                updates.append("contrasena_hash = %s")
                params.append(contrasena_hash)
            
            if not updates:
                return False, "No hay datos para actualizar"
            
            params.append(usuario_id)
            set_clause = ", ".join(updates)
            query = f"UPDATE usuarios SET {set_clause} WHERE id = %s RETURNING id, nombre, correo;"
            
            resultado = self.db.execute_query(query, params)
            
            if resultado:
                return True, resultado[0]
            else:
                return False, "Usuario no encontrado"

        except Exception as e:
            if "duplicate key value" in str(e):
                return False, "El correo electrónico ya está en uso"
            return False, f"Error del sistema: {str(e)}"

    def eliminar_usuario(self, usuario_id):
        """Elimina un usuario por su ID"""
        try:
            query = "DELETE FROM usuarios WHERE id = %s RETURNING id;"
            resultado = self.db.execute_query(query, (usuario_id,))
            
            if resultado:
                return True, "Usuario eliminado correctamente"
            else:
                return False, "Usuario no encontrado"

        except Exception as e:
            return False, f"Error del sistema: {str(e)}"