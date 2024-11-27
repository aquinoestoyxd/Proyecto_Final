import os
from flask import Flask, render_template, jsonify, request
import pymysql
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)

def get_db_connection():
    connection = pymysql.connect(
        host=os.getenv('MYSQL_HOST'),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        db=os.getenv('MYSQL_DB'),
        port=int(os.getenv('MYSQL_PORT')),
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection

NEO4J_URI = os.getenv('NEO4J_URI')
NEO4J_USER = os.getenv('NEO4J_USER')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD')

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def get_neo4j_connection():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def obtener_grafo():
    session = driver.session()
    query = """
        MATCH (n)-[r]->(m)
        RETURN n, r, m
    """
    result = session.run(query)
    
    # Procesar los resultados para hacerlos adecuados para Vis.js
    nodes = []
    edges = []
    
    # Extraer nodos y relaciones de los resultados
    for record in result:
        node_1 = record["n"]
        node_2 = record["m"]
        relationship = record["r"]
        
        # Crear nodos
        if not any(node["id"] == node_1.element_id for node in nodes):
            nodes.append({
                "id": node_1.element_id,
                "label": node_1["name"],
                "properties": dict(node_1)  # Guardamos todas las propiedades del nodo
            })
        if not any(node["id"] == node_2.element_id for node in nodes):
            nodes.append({
                "id": node_2.element_id,
                "label": node_2["name"],
                "properties": dict(node_2)  # Guardamos todas las propiedades del nodo
            })
        
        # Crear relación
        edges.append({
            "from": node_1.element_id,
            "to": node_2.element_id,
            "label": relationship.type,
            "properties": dict(relationship)  # Guardamos las propiedades de la relación
        })
    
    session.close()
    
    return {"nodes": nodes, "edges": edges}

@app.route('/grafo')
def grafo():
    grafo_data = obtener_grafo()
    return render_template('grafo.html', grafo_data=grafo_data)

@app.route('/')
def index():
    connection = get_db_connection()
    
    with connection.cursor() as cursor:
        cursor.execute('''
        SELECT ip.idInformacionPersona AS ID, ip.Nombre, ip.Apellido, ip.DNI, cp.NombreCarrera AS Carrera, cpi.CicloPromedio AS Ciclo, f.NombreFacultad AS Facultad, u.Nombre AS Universidad
        FROM InformacionPersona ip
        JOIN CarreraProfesional_has_InformacionPersona cpi ON ip.idInformacionPersona = cpi.InformacionPersona_idInformacionPersona
        JOIN CarreraProfesional cp ON cpi.CarreraProfesional_idCarreraProfesional = cp.idCarreraProfesional
        JOIN Facultad f ON cp.Facultad_idFacultad = f.idFacultad
        JOIN Universidad u ON f.idUniversidad = u.idUniversidad;
        ''')
        resultados = cursor.fetchall()  # Obtiene todas las categorías

    connection.close()

    # Pasamos las categorías al template
    return render_template('index.html', resultados=resultados)

@app.route('/relaciones')
def relaciones():
    return render_template('relaciones.html')

@app.route('/pagina')
def pagina():
    return render_template('pagina.html')

@app.route('/get_all_people', methods=['GET'])
def get_all_people():
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('''SELECT idInformacionPersona AS ID, Nombre, Apellido, DNI
                          FROM InformacionPersona''')
        results = cursor.fetchall()
    connection.close()
    return jsonify(results)

# Insertar una nueva persona

@app.route('/post', methods=['GET', 'POST'])
def post():
    if request.method == 'POST':
        # Manejar la lógica de inserción aquí
        data = request.form
        nombre = data.get('nombre')
        apellido = data.get('apellido')
        dni = data.get('dni')
        carrera_id = data.get('carrera')

        # Inserción en MySQL
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO InformacionPersona (Nombre, Apellido, DNI) VALUES (%s, %s, %s)', (nombre, apellido, dni))
            persona_id = cursor.lastrowid
            cursor.execute('INSERT INTO CarreraProfesional_has_InformacionPersona (CarreraProfesional_idCarreraProfesional, InformacionPersona_idInformacionPersona) VALUES (%s, %s)', (carrera_id, persona_id))
            connection.commit()
        connection.close()

        # Inserción en Neo4j
        try:
            with driver.session() as session:
                session.run(
                    """
                    CREATE (p:Persona {name: $nombre, apellido: $apellido, dni: $dni})
                    WITH p
                    MATCH (c:Carrera {id: $carrera_id})
                    MERGE (p)-[:ESTUDIANTE_DE]->(c)
                    WITH p, c
                    MATCH (f:Facultad)<-[:PERTENECE_A]-(c)
                    MERGE (p)-[:PERTENECE_A]->(f)
                    """,
                    {
                        'nombre': nombre,
                        'apellido': apellido,
                        'dni': dni,
                        'carrera_id': carrera_id
                    }
                )
        except Exception as e:
            print(f"Error al insertar en Neo4j: {e}")
            return jsonify({"error": "Error al insertar en Neo4j"}), 500

        return jsonify({"message": "Persona añadida correctamente"}), 200

    return render_template('post.html')

@app.route('/get_universidades', methods=['GET'])
def get_universidades():
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('SELECT idUniversidad, Nombre FROM Universidad')
        results = cursor.fetchall()
    connection.close()
    return jsonify(results)

@app.route('/get_facultades/<int:universidad_id>', methods=['GET'])
def get_facultades(universidad_id):
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('SELECT idFacultad, NombreFacultad FROM Facultad WHERE idUniversidad = %s', (universidad_id,))
        results = cursor.fetchall()
    connection.close()
    return jsonify(results)

@app.route('/get_carreras/<int:facultad_id>', methods=['GET'])
def get_carreras(facultad_id):
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('SELECT idCarreraProfesional, NombreCarrera FROM CarreraProfesional WHERE Facultad_idFacultad = %s', (facultad_id,))
        results = cursor.fetchall()
    connection.close()
    return jsonify(results)

@app.route('/insertar', methods=['POST'])
def insertar():
    data = request.form
    nombre = data.get('nombre')
    apellido = data.get('apellido')
    dni = data.get('dni')
    carrera_id = data.get('carrera')
    ciclo = data.get('ciclo')

    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO InformacionPersona (Nombre, Apellido, DNI) VALUES (%s, %s, %s)', (nombre, apellido, dni))
        persona_id = cursor.lastrowid
        cursor.execute('INSERT INTO CarreraProfesional_has_InformacionPersona (CarreraProfesional_idCarreraProfesional, InformacionPersona_idInformacionPersona, CicloPromedio) VALUES (%s, %s, %s)', (carrera_id, persona_id, ciclo))
        connection.commit()

        # Obtener la etiqueta de la universidad
        cursor.execute('''
            SELECT u.Nombre
            FROM Universidad u
            JOIN Facultad f ON u.idUniversidad = f.idUniversidad
            JOIN CarreraProfesional cp ON f.idFacultad = cp.Facultad_idFacultad
            WHERE cp.idCarreraProfesional = %s
        ''', (carrera_id,))
        universidad = cursor.fetchone()['Nombre']

    connection.close()

    # Determinar la etiqueta de la persona basada en la universidad
    if universidad == "UPCH":
        etiqueta = "Herediano"
    elif universidad == "ULima":
        etiqueta = "Limenos"
    elif universidad == "UP":
        etiqueta = "Pacifico"
    elif universidad == "PUCP":
        etiqueta = "Catos"
    else:
        etiqueta = "Estudiante"

    # Insertar en Neo4j
    session = driver.session()
    query = """
    MATCH (f:Facultad)-[:PERTENECE_A]->(u:Universidad {Nombre: $universidad})
    CREATE (p:%s {id: $id, nombre: $nombre, apellido: $apellido, dni: $dni, ciclo: $ciclo})
    CREATE (p)-[:ESTUDIANTE_DE]->(f)
    """ % etiqueta
    session.run(query, {
        'id': persona_id,
        'nombre': nombre,
        'apellido': apellido,
        'dni': dni,
        'ciclo': ciclo,
        'universidad': universidad
    })
    session.close()

    return jsonify({"message": "Persona agregada correctamente"}), 200

# Eliminar

@app.route('/eliminar', methods=['GET', 'POST'])
def eliminar():
    if request.method == 'POST':
        data = request.form
        dni = data.get('dni')

        connection = get_db_connection()
        with connection.cursor() as cursor:
            # Eliminar la relación en CarreraProfesional_has_InformacionPersona
            cursor.execute('DELETE FROM CarreraProfesional_has_InformacionPersona WHERE InformacionPersona_idInformacionPersona = (SELECT idInformacionPersona FROM InformacionPersona WHERE DNI = %s)', (dni,))
            # Eliminar la persona en InformacionPersona
            cursor.execute('DELETE FROM InformacionPersona WHERE DNI = %s', (dni,))
            connection.commit()
        connection.close()

        return jsonify({"message": "Persona eliminada correctamente"}), 200

    return render_template('eliminar.html')

# Limpiar

@app.route('/clear_relations', methods=['POST'])
def clear_relations():
    data = request.get_json()
    person_id = data.get('person_id')

    # Eliminar relaciones en Neo4j
    session = driver.session()
    query = """
    MATCH (p {id: $person_id})-[r]-()
    DELETE r
    """
    session.run(query, {'person_id': person_id})
    session.close()

    return jsonify({"message": "Relaciones eliminadas correctamente"}), 200

# Actualizar 

@app.route('/update', methods=['GET', 'PUT'])
def update():
    if request.method == 'GET':
        return render_template('actualizar.html')
    
    data = request.json
    nombre = data.get('nombre')
    apellido = data.get('apellido')
    dni = data.get('dni')
    nuevo_dni = data.get('nuevo_dni')
    ciclo = data.get('ciclo')
    carrera_id = data.get('carrera')

    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('''
            UPDATE InformacionPersona
            SET Nombre = %s, Apellido = %s, DNI = %s
            WHERE DNI = %s
        ''', (nombre, apellido, nuevo_dni, dni))
        cursor.execute('''
            UPDATE CarreraProfesional_has_InformacionPersona
            SET CarreraProfesional_idCarreraProfesional = %s, CicloPromedio = %s
            WHERE InformacionPersona_idInformacionPersona = (SELECT idInformacionPersona FROM InformacionPersona WHERE DNI = %s)
        ''', (carrera_id, ciclo, nuevo_dni))
        connection.commit()
    connection.close()

    # Actualizar en Neo4j
    session = driver.session()
    query = """
    MATCH (p {dni: $dni})
    SET p.nombre = $nombre, p.apellido = $apellido, p.dni = $nuevo_dni, p.ciclo = $ciclo
    WITH p
    MATCH (p)-[r:ESTUDIANTE_DE]->(c)
    DELETE r
    WITH p
    MATCH (c:Carrera {id: $carrera_id})
    CREATE (p)-[:ESTUDIANTE_DE]->(c)
    """
    session.run(query, {
        'dni': dni,
        'nombre': nombre,
        'apellido': apellido,
        'nuevo_dni': nuevo_dni,
        'ciclo': ciclo,
        'carrera_id': carrera_id
    })
    session.close()

    return jsonify({"message": "Información actualizada correctamente"}), 200

@app.route('/get_persona/<dni>', methods=['GET'])
def get_persona(dni):
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('''
            SELECT ip.Nombre, ip.Apellido, ip.DNI, cpi.CicloPromedio AS Ciclo, cp.idCarreraProfesional AS Carrera_idCarreraProfesional, f.idFacultad AS Facultad_idFacultad
            FROM InformacionPersona ip
            JOIN CarreraProfesional_has_InformacionPersona cpi ON ip.idInformacionPersona = cpi.InformacionPersona_idInformacionPersona
            JOIN CarreraProfesional cp ON cpi.CarreraProfesional_idCarreraProfesional = cp.idCarreraProfesional
            JOIN Facultad f ON cp.Facultad_idFacultad = f.idFacultad
            WHERE ip.DNI = %s
        ''', (dni,))
        result = cursor.fetchone()
    connection.close()

    if result:
        return jsonify(result)
    else:
        return jsonify({"error": "Persona no encontrada"}), 404

if __name__ == '__main__':
    app.run(debug=True)