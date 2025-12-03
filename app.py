from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import logging
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor


# Importaciones para Groq
from groq import Groq



# ===== NUEVAS IMPORTACIONES PARA IMÁGENES =====
import base64
from io import BytesIO
from PIL import Image


# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'eco-plagas-secret-key-2025')

# Configuración de la base de datos
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'mi_base_datos'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '')
}

# 1. Cargar claves de API
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# 2. OpenWeatherMap API Key (Clima)
API_KEY_CLIMA = '37162e8529a3d41fc6157bf746bc6ac1'
BASE_URL_CLIMA = 'http://api.openweathermap.org/data/2.5/weather'

# --- CONFIGURACIÓN DE LA IA (GROQ) ---
if not GROQ_API_KEY:
    logger.error("ADVERTENCIA: La clave GROQ_API_KEY no está configurada en .env. El chatbot no funcionará.")
    client = None
else:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        logger.info("Cliente de IA (Groq) inicializado correctamente.")
    except Exception as e:
        logger.error(f"Error al inicializar el cliente de Groq: {e}")
        client = None

# Función para conexión a la base de datos
def get_db_connection():
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        return connection
    except Exception as e:
        logger.error(f"Error conectando a la base de datos: {e}")
        return None

# Función para crear las tablas si no existen
def create_tables():
    connection = get_db_connection()
    if connection:
        try:
            with connection.cursor() as cursor:
                # Tabla de usuarios
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS usuarios (
                        id SERIAL PRIMARY KEY,
                        nombre VARCHAR(100) NOT NULL,
                        correo VARCHAR(255) UNIQUE NOT NULL,
                        contrasena_hash VARCHAR(255) NOT NULL,
                        fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Tabla de plantas
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS plantas (
                        id SERIAL PRIMARY KEY,
                        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
                        nombre VARCHAR(100) NOT NULL,
                        especie VARCHAR(100),
                        ubicacion VARCHAR(100),
                        luz VARCHAR(50),
                        riego VARCHAR(50),
                        estado VARCHAR(50) DEFAULT 'saludable',
                        notas TEXT,
                        icono VARCHAR(10) DEFAULT '🌱',
                        fecha_agregada TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                connection.commit()
                logger.info("Tablas verificadas/creadas correctamente")
        except Exception as e:
            logger.error(f"Error creando tablas: {e}")
        finally:
            connection.close()

# Crear tablas al iniciar la aplicación
create_tables()

# RUTAS DE AUTENTICACIÓN
@app.route('/api/registro', methods=['POST'])
def registro():
    data = request.json
    nombre = data.get('nombre', '').strip()
    correo = data.get('correo', '').strip()
    contrasena = data.get('contrasena', '')

    if not nombre or not correo or not contrasena:
        return jsonify({'error': 'Todos los campos son obligatorios'}), 400

    if len(contrasena) < 6:
        return jsonify({'error': 'La contraseña debe tener al menos 6 caracteres'}), 400

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Error de conexión a la base de datos'}), 500

    try:
        contrasena_hash = generate_password_hash(contrasena)
        
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO usuarios (nombre, correo, contrasena_hash) VALUES (%s, %s, %s) RETURNING id, nombre, correo, fecha_creacion;",
                (nombre, correo, contrasena_hash)
            )
            resultado = cursor.fetchone()
            connection.commit()
            
            usuario = {
                'id': resultado[0],
                'nombre': resultado[1],
                'correo': resultado[2],
                'fecha_creacion': resultado[3].isoformat() if resultado[3] else None
            }
            
            # Iniciar sesión automáticamente
            session['usuario_id'] = usuario['id']
            session['usuario_nombre'] = usuario['nombre']
            session['usuario_correo'] = usuario['correo']
            
            return jsonify({
                'success': True,
                'message': 'Usuario registrado exitosamente',
                'usuario': usuario,
                'redirect': '/usuario'
            })
            
    except psycopg2.IntegrityError:
        return jsonify({'error': 'El correo electrónico ya está registrado'}), 400
    except Exception as e:
        logger.error(f"Error en registro: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        connection.close()

@app.route('/api/login', methods=['GET', 'POST'])
def login():
    # ----- MÉTODO GET -----
    if request.method == 'GET':
        if 'usuario_id' in session:
            return jsonify({
                'logged_in': True,
                'usuario': {
                    'id': session.get('id'),
                    'nombre': session.get('nombre'),
                    'correo': session.get('correo')
                }
            })
        else:
            return jsonify({'logged_in': False})

    # ----- MÉTODO POST -----
    if request.method == 'POST':
        data = request.json
        correo = data.get('correo', '').strip()
        contrasena = data.get('contrasena_hash', '')

        if not correo or not contrasena:
            return jsonify({'error': 'Correo y contraseña son obligatorios'}), 400

        connection = get_db_connection()
        if not connection:
            return jsonify({'error': 'Error de conexión a la base de datos'}), 500

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, nombre, correo, contrasena_hash, fecha_creacion FROM usuarios WHERE correo = %s;",
                    (correo,)
                )
                resultado = cursor.fetchone()

                if not resultado:
                    return jsonify({'error': 'Credenciales incorrectas'}), 401

                usuario_id, nombre, correo_db, contrasena_hash, fecha_creacion = resultado

                if check_password_hash(contrasena_hash, contrasena):
                    session['id'] = usuario_id
                    session['nombre'] = nombre
                    session['correo'] = correo_db

                    usuario = {
                        'id': usuario_id,
                        'nombre': nombre,
                        'correo': correo_db,
                        'fecha_creacion': fecha_creacion.isoformat() if fecha_creacion else None
                    }

                    return jsonify({
                        'success': True,
                        'message': 'Inicio de sesión exitoso',
                        'usuario': usuario,
                        'redirect': '/usuario'
                    })
                else:
                    return jsonify({'error': 'Credenciales incorrectas'}), 401

        except Exception as e:
            logger.error(f"Error en login: {e}")
            return jsonify({'error': 'Error interno del servidor'}), 500
        finally:
            connection.close()

@app.route('/logout')
def logout():
    """Ruta directa para cerrar sesión (enlaces HTML)"""
    session.clear()
    return redirect('/')

@app.route('/api/usuario_actual', methods=['GET'])
def usuario_actual():
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    return jsonify({
        'id': session['usuario_id'],
        'nombre': session['usuario_nombre'],
        'correo': session['usuario_correo']
    })

# RUTAS PRINCIPALES
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/usuario')
def usuario():
    if 'usuario_id' not in session:
        return redirect('/')
    return render_template('usuario.html', nombre_usuario=session.get('usuario_nombre', 'Usuario'))

@app.route('/perfil')
def perfil():
    if 'usuario_id' not in session:
        return redirect('/')
    return render_template('Perfil.html', nombre_usuario=session.get('usuario_nombre', 'Usuario'))

@app.route('/configuracion')
def configuracion():
    if 'usuario_id' not in session:
        return redirect('/')
    return render_template('configuracion.html', nombre_usuario=session.get('usuario_nombre', 'Usuario'))

@app.route('/clima', methods=['POST'])
def obtener_clima():
    ciudad = request.json.get('ciudad', '')
    
    if not ciudad:
        return jsonify({'error': 'Por favor ingresa una ciudad'}), 400
    
    try:
        params = {
            'q': ciudad,
            'appid': API_KEY_CLIMA,
            'units': 'metric',
            'lang': 'es'
        }
        
        response = requests.get(BASE_URL_CLIMA, params=params)
        data = response.json()
        
        if response.status_code == 200:
            clima_info = {
                'ciudad': data['name'],
                'pais': data['sys']['country'],
                'temperatura': round(data['main']['temp']),
                'sensacion': round(data['main']['feels_like']),
                'descripcion': data['weather'][0]['description'].capitalize(),
                'humedad': data['main']['humidity'],
                'viento': data['wind']['speed'],
                'icono': data['weather'][0]['icon']
            }
            return jsonify(clima_info)
        else:
            return jsonify({'error': 'Ciudad no encontrada'}), 404
            
    except Exception as e:
        logger.error(f"Error en el clima: {e}")
        return jsonify({'error': 'Error al obtener datos del clima'}), 500

# ===== RUTA API PARA EL CHATBOT CON SOPORTE DE IMÁGENES =====
@app.route('/api/chatbot', methods=['POST'])
def handle_chatbot():
    if not client:
        return jsonify({'response': 'Error de configuración: El servicio de IA no está disponible.'}), 500
    
    try:
        # Verificar si es multipart/form-data (con imagen) o JSON (solo texto)
        if request.content_type and 'multipart/form-data' in request.content_type:
            user_message = request.form.get('message', '')
            image_file = request.files.get('image')
            
            if not user_message and not image_file:
                return jsonify({'response': 'Por favor, escribe un mensaje o adjunta una imagen.'}), 400
            
            # Procesar imagen si existe
            if image_file:
                try:
                    # Leer bytes originales
                    image_bytes = image_file.read()

                    # Procesar (validar/converter/redimensionar) antes de enviar al modelo
                    try:
                        processed_bytes, mime_type = process_image_bytes(image_bytes, max_size=(1024, 1024), output_format='JPEG', quality=85)
                    except Exception as proc_err:
                        logger.warning(f"Procesamiento con Pillow falló, intentando usar bytes originales: {proc_err}")
                        processed_bytes = image_bytes
                        mime_type = image_file.content_type or 'image/jpeg'

                    base64_image = base64.b64encode(processed_bytes).decode('utf-8')

                    # Construir el mensaje con la imagen embebida en data URI
                    content = [
                        {
                            "type": "text",
                            "text": user_message or "Analiza esta imagen de planta. Identifica si tiene alguna plaga o enfermedad y proporciona recomendaciones de tratamiento."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]

                    # Usar modelo con visión
                    model = "llama-3.2-90b-vision-preview"

                    logger.info(f"Procesada imagen para análisis de plagas (mime={mime_type}, bytes={len(processed_bytes)})")

                except Exception as img_error:
                    logger.error(f"Error procesando imagen: {img_error}")
                    return jsonify({'response': 'Error al procesar la imagen. Intenta con otra imagen.'}), 400
            else:
                content = user_message
                model = "llama-3.3-70b-versatile"
        else:
            # Solicitud JSON tradicional (solo texto)
            data = request.json
            user_message = data.get('message')
            
            if not user_message:
                return jsonify({'response': 'Por favor, escribe un mensaje.'}), 400
            
            content = user_message
            model = "llama-3.3-70b-versatile"

        # Llamada a la API de Groq
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system", 
                    "content": """Eres un experto agrónomo y botánico especializado en:

🌱 IDENTIFICACIÓN DE PLANTAS
- Reconoces especies de plantas por sus características visuales
- Identificas el estado de salud de las plantas

🐛 DETECCIÓN DE PLAGAS Y ENFERMEDADES
- Identificas plagas comunes: pulgones, cochinillas, ácaros, mosca blanca, orugas
- Detectas enfermedades: hongos, manchas foliares, podredumbre, virus
- Evalúas el nivel de severidad (leve, moderado, severo, crítico)

💊 TRATAMIENTOS Y SOLUCIONES
- Recomiendas tratamientos ORGÁNICOS como primera opción (jabón potásico, aceite de neem, tierra de diatomeas)
- Sugieres tratamientos químicos solo cuando es necesario, con precauciones
- Das instrucciones paso a paso de aplicación

🌿 PREVENCIÓN Y CUIDADOS
- Aconsejas sobre riego, luz, sustrato y nutrición
- Explicas medidas preventivas contra plagas
- Recomiendas plantas compañeras y control biológico

FORMATO DE RESPUESTA:
Usa emojis para organizar la información:
- 🔍 para identificación
- ⚠️ para diagnóstico/problemas
- 💊 para tratamientos
- ✅ para recomendaciones/prevención
- 📋 para instrucciones paso a paso

Sé claro, práctico y amigable. Usa párrafos cortos y separados con líneas en blanco para mejor legibilidad."""
                },
                {
                    "role": "user", 
                    "content": content
                }
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        ai_response = completion.choices[0].message.content
        
        logger.info(f"Usuario: {user_message if isinstance(content, str) else 'Imagen + ' + content[0]['text']}")
        logger.info(f"IA (Groq): {ai_response[:100]}...")
        
        return jsonify({
            'response': ai_response,
            'model': model
        })

    except Exception as e:
        logger.error(f"Error en la llamada a la API de Groq: {e}")
        
        if "authentication" in str(e).lower():
            error_msg = "Error de autenticación: Verifica tu GROQ_API_KEY en el archivo .env"
        elif "rate limit" in str(e).lower():
            error_msg = "Límite de tasa excedido. Intenta de nuevo en unos momentos."
        elif "quota" in str(e).lower() or "429" in str(e):
            error_msg = "Cuota excedida. Verifica tu plan en Groq."
        elif "image" in str(e).lower():
            error_msg = "Error al analizar la imagen. Asegúrate de que sea una imagen válida de una planta."
        else:
            error_msg = f"Error al comunicarme con la IA. Intenta de nuevo."
            
        return jsonify({'response': error_msg}), 500
    
    # Helper: procesar imagenes recibidas (validar, convertir a RGB, redimensionar y re-encodear)
    
def process_image_bytes(image_bytes, max_size=(1024, 1024), output_format='JPEG', quality=85):
    """Procesa bytes de imagen y retorna (processed_bytes, mime_type).

    - Convierte a RGB
    - Redimensiona manteniendo aspecto si supera max_size
    - Guarda en formato output_format con la calidad indicada
    """
    try:
        buf = BytesIO(image_bytes)
        img = Image.open(buf)
        img.load()

        # Convertir a RGB para evitar problemas con paletas/alpha
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Redimensionar si es muy grande
        img.thumbnail(max_size, Image.LANCZOS)

        out = BytesIO()
        img.save(out, format=output_format, quality=quality)
        processed = out.getvalue()
        mime = 'image/jpeg' if output_format.upper() == 'JPEG' else f'image/{output_format.lower()}'
        return processed, mime
    except Exception as e:
        logger.error(f"Error procesando bytes de imagen: {e}")
        raise

# API para gestionar plantas
@app.route('/api/plantas', methods=['GET', 'POST'])
def gestionar_plantas():
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Error de conexión a la base de datos'}), 500

    try:
        if request.method == 'GET':
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT * FROM plantas WHERE usuario_id = %s ORDER BY fecha_agregada DESC;",
                    (session['usuario_id'],)
                )
                plantas = cursor.fetchall()
                
                for planta in plantas:
                    if planta['fecha_agregada']:
                        planta['fecha_agregada'] = planta['fecha_agregada'].isoformat()
                
                return jsonify(plantas)
        
        elif request.method == 'POST':
            data = request.json
            
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO plantas (usuario_id, nombre, especie, ubicacion, luz, riego, notas, icono)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *;
                """, (
                    session['usuario_id'],
                    data.get('nombre'),
                    data.get('especie'),
                    data.get('ubicacion'),
                    data.get('luz'),
                    data.get('riego'),
                    data.get('notas', ''),
                    data.get('icono', '🌱')
                ))
                
                nueva_planta = cursor.fetchone()
                connection.commit()
                
                if nueva_planta['fecha_agregada']:
                    nueva_planta['fecha_agregada'] = nueva_planta['fecha_agregada'].isoformat()
                
                return jsonify({'success': True, 'planta': nueva_planta})
                
    except Exception as e:
        logger.error(f"Error gestionando plantas: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        connection.close()

@app.route('/api/plantas/<int:planta_id>', methods=['PUT', 'DELETE'])
def gestionar_planta_individual(planta_id):
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Error de conexión a la base de datos'}), 500

    try:
        if request.method == 'PUT':
            data = request.json
            
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                campos = []
                valores = []
                for key, value in data.items():
                    if key in ['nombre', 'especie', 'ubicacion', 'luz', 'riego', 'estado', 'notas', 'icono']:
                        campos.append(f"{key} = %s")
                        valores.append(value)
                
                if not campos:
                    return jsonify({'error': 'No hay campos válidos para actualizar'}), 400
                
                valores.extend([planta_id, session['usuario_id']])
                query = f"UPDATE plantas SET {', '.join(campos)} WHERE id = %s AND usuario_id = %s RETURNING *;"
                
                cursor.execute(query, valores)
                planta_actualizada = cursor.fetchone()
                connection.commit()
                
                if not planta_actualizada:
                    return jsonify({'error': 'Planta no encontrada'}), 404
                
                if planta_actualizada['fecha_agregada']:
                    planta_actualizada['fecha_agregada'] = planta_actualizada['fecha_agregada'].isoformat()
                
                return jsonify({'success': True, 'planta': planta_actualizada})
        
        elif request.method == 'DELETE':
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM plantas WHERE id = %s AND usuario_id = %s RETURNING id;",
                    (planta_id, session['usuario_id'])
                )
                resultado = cursor.fetchone()
                connection.commit()
                
                if resultado:
                    return jsonify({'success': True, 'message': 'Planta eliminada correctamente'})
                else:
                    return jsonify({'error': 'Planta no encontrada'}), 404
                    
    except Exception as e:
        logger.error(f"Error gestionando planta individual: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        connection.close()

# API para recordatorios
@app.route('/api/recordatorios', methods=['GET'])
def gestionar_recordatorios():
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Error de conexión a la base de datos'}), 500

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT id, nombre, riego FROM plantas WHERE usuario_id = %s;",
                (session['usuario_id'],)
            )
            plantas = cursor.fetchall()
            
            recordatorios = []
            for planta in plantas:
                recordatorios.append({
                    'planta': planta['nombre'],
                    'tipo': 'riego',
                    'frecuencia': planta.get('riego', 'semanal'),
                    'proximo': calcular_proximo_riego(planta.get('riego', 'semanal')),
                    'icono': '💧'
                })
                
                recordatorios.append({
                    'planta': planta['nombre'],
                    'tipo': 'fertilizacion',
                    'frecuencia': 'mensual',
                    'proximo': calcular_proximo_fertilizacion(),
                    'icono': '🌱'
                })
            
            return jsonify(recordatorios)
            
    except Exception as e:
        logger.error(f"Error obteniendo recordatorios: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        connection.close()

def calcular_proximo_riego(frecuencia):
    hoy = datetime.now()
    if frecuencia == 'diario':
        return (hoy + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
    elif frecuencia == '2-3-dias':
        return (hoy + timedelta(days=2)).strftime('%Y-%m-%d %H:%M')
    elif frecuencia == 'semanal':
        return (hoy + timedelta(days=7)).strftime('%Y-%m-%d %H:%M')
    elif frecuencia == '15-dias':
        return (hoy + timedelta(days=15)).strftime('%Y-%m-%d %H:%M')
    else:  # mensual
        return (hoy + timedelta(days=30)).strftime('%Y-%m-%d %H:%M')

def calcular_proximo_fertilizacion():
    hoy = datetime.now()
    if hoy.month == 12:
        proximo_mes = hoy.replace(year=hoy.year + 1, month=1, day=1)
    else:
        proximo_mes = hoy.replace(month=hoy.month + 1, day=1)
    return proximo_mes.strftime('%Y-%m-%d %H:%M')

@app.route('/api/check_auth')
def check_auth():
    if 'usuario_id' in session:
        return jsonify({
            'authenticated': True,
            'usuario': {
                'id': session['usuario_id'],
                'nombre': session['usuario_nombre'],
                'correo': session['usuario_correo']
            }
        })
    else:
        return jsonify({'authenticated': False})

if __name__ == '__main__':

    app.run(debug=True)

