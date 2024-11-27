from flask import Flask, request, render_template, redirect, url_for, jsonify
import pymysql
from dotenv import load_dotenv
import os
import neo4j
from neo4j import GraphDatabase

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
        if not any(node["id"] == node_1.id for node in nodes):
            nodes.append({
                "id": node_1.id,
                "label": node_1["name"],
                "properties": dict(node_1)  # Guardamos todas las propiedades del nodo
            })
        if not any(node["id"] == node_2.id for node in nodes):
            nodes.append({
                "id": node_2.id,
                "label": node_2["name"],
                "properties": dict(node_2)  # Guardamos todas las propiedades del nodo
            })
        
        # Crear relación
        edges.append({
            "from": node_1.id,
            "to": node_2.id,
            "label": relationship.type,
            "properties": dict(relationship)  # Guardamos las propiedades de la relación
        })
    
    session.close()
    
    return {"nodes": nodes, "edges": edges}

@app.route('/grafo')
def grafo():
    grafo_data = obtener_grafo()
    return render_template('grafo.html', grafo_data=grafo_data)

@app.route('/borrar', methods=['DELETE'])
def borrar():
    # Obtener los datos del cuerpo de la solicitud (JSON)
    data = request.get_json()

    # Obtener el nombre de la entidad desde el JSON
    nombre_entidad = data.get('nombre_entidad')  # Asegúrate de que la clave sea 'nombre_entidad'

    # Verificar si se proporcionó el nombre de la entidad
    if not nombre_entidad:
        return jsonify({"error": "El nombre de la entidad es requerido"}), 400

    # Aquí colocas la lógica para borrar la entidad de la base de datos SQL
    # Por ejemplo, si estás eliminando una persona de la tabla `Personas`:
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('DELETE FROM InformacionPersona WHERE Nombre = %s', (nombre_entidad,))
        connection.commit()

    connection.close()

    # Aquí colocas la lógica para borrar la entidad de Neo4j
    session = driver.session()
    query = """
        MATCH (n {name: $nombre_entidad})
        DELETE n
    """
    session.run(query, nombre_entidad=nombre_entidad)
    session.close()

    # Respuesta de éxito
    return jsonify({"message": f"Entidad {nombre_entidad} eliminada exitosamente"}), 200

@app.route('/actualizar', methods=['PUT'])
def actualizar():
    # Obtener los datos del cuerpo de la solicitud (body) en formato JSON
    data = request.get_json()
    
    # Asegurarse de que los campos 'nombre' y 'dni' estén presentes para identificar la persona
    nombre = data.get('nombre')
    dni = data.get('dni')
    
    if not nombre or not dni:
        return jsonify({"error": "Faltan datos necesarios"}), 400
    
    # Obtener los valores opcionales
    nuevo_nombre = data.get('nuevo_nombre', None)
    nuevo_dni = data.get('nuevo_dni', None)
    nueva_carrera = data.get('nueva_carrera', None)
    nuevo_ciclo = data.get('nuevo_ciclo', None)

    # Actualizar en la base de datos SQL
    connection = get_db_connection()
    with connection.cursor() as cursor:
        sql = "UPDATE InformacionPersona SET"
        params = []

        if nuevo_dni:
            sql += " DNI = %s,"
            params.append(nuevo_dni)
        
        if nuevo_nombre:
            sql += " Nombre = %s,"
            params.append(nuevo_nombre)
        
        if nueva_carrera:
            sql += " Carrera = %s,"
            params.append(nueva_carrera)
        
        if nuevo_ciclo:
            sql += " CicloPromedio = %s,"
            params.append(nuevo_ciclo)

        # Eliminar la última coma
        sql = sql.rstrip(',')
        
        # Asegurarse de que estamos actualizando la persona correcta
        sql += " WHERE Nombre = %s AND DNI = %s"
        params.extend([nombre, dni])
        
        cursor.execute(sql, tuple(params))
        connection.commit()

    # Ahora actualizamos en la base de datos de Neo4j
    session = driver.session()

    query = "MATCH (p:Catos {DNI: $dni, name: $nombre})"
    query_params = {
        'dni': dni,
        'nombre': nombre
    }

    # Modificar solo los campos que vienen en la solicitud
    if nuevo_dni:
        query += " SET p.DNI = $nuevo_dni"
        query_params['nuevo_dni'] = nuevo_dni
        
    if nuevo_nombre:
        query += ", p.name = $nuevo_nombre"
        query_params['nuevo_nombre'] = nuevo_nombre
        
    if nueva_carrera:
        query += ", p.Carrera = $nueva_carrera"
        query_params['nueva_carrera'] = nueva_carrera
        
    if nuevo_ciclo:
        query += ", p.CicloPromedio = $nuevo_ciclo"
        query_params['nuevo_ciclo'] = nuevo_ciclo
    
    # Ejecutar la consulta Cypher para actualizar los datos en Neo4j
    session.run(query, query_params)
    session.close()

    # Respuesta exitosa
    return jsonify({"message": "Datos actualizados correctamente"}), 200

if __name__ == '__main__':
    app.run(debug=True)