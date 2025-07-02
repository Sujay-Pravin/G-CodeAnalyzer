import os
import json
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, Neo4jError
import vertexai
from vertexai.language_models import TextEmbeddingModel
from vertexai.generative_models import GenerativeModel
from google.api_core.exceptions import GoogleAPIError # For more general Vertex AI/Google Cloud errors

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# --- Logging Configuration ---
# Set up a basic logger for the Flask app
# In a production environment, you'd configure this more robustly
# (e.g., to write to files, send to a log aggregation service)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
app.logger.info("Flask app starting up...")

# --- Environment Variable Validation and Global Initializations ---
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_REGION = os.getenv("GCP_REGION")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Log Neo4j connection info (mask password)
app.logger.info(f"Neo4j URI: {NEO4J_URI}, Username: {NEO4J_USERNAME}")

# Validate environment variables critical for startup
if not GCP_PROJECT_ID:
    app.logger.critical("GCP_PROJECT_ID environment variable not set. Exiting.")
    exit(1) # Exit if critical config is missing
if not GCP_REGION:
    app.logger.critical("GCP_REGION environment variable not set. Exiting.")
    exit(1)
if not NEO4J_URI:
    app.logger.critical("NEO4J_URI environment variable not set. Exiting.")
    exit(1)
if not NEO4J_USERNAME:
    app.logger.critical("NEO4J_USERNAME environment variable not set. Exiting.")
    exit(1)
if not NEO4J_PASSWORD:
    app.logger.critical("NEO4J_PASSWORD environment variable not set. Exiting.")
    exit(1)

# Initialize Vertex AI
try:
    vertexai.init(project=GCP_PROJECT_ID, location="us-central1")
    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    generative_model = GenerativeModel("gemini-2.5-flash")
    app.logger.info(f"Vertex AI initialized for project '{GCP_PROJECT_ID}' in region '{GCP_REGION}'.")
except GoogleAPIError as e:
    app.logger.critical(f"Failed to initialize Vertex AI or load models: {e}", exc_info=True)
    exit(1) # Exit if Vertex AI initialization fails (critical dependency)
except Exception as e:
    app.logger.critical(f"An unexpected error occurred during Vertex AI initialization: {e}", exc_info=True)
    exit(1)

# Neo4j connection - Initialized once globally
neo4j_driver = None

def get_neo4j_driver():
    """
    Returns a singleton Neo4j driver instance.
    Establishes a plain connection using the provided URI and credentials.
    """
    global neo4j_driver
    if neo4j_driver is None:
        try:
            neo4j_driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
            )
            neo4j_driver.verify_connectivity() # Test the connection
            app.logger.info("Neo4j driver initialized and connected successfully.")
            # Ensure GDS vector indexes exist
            create_vector_indexes(neo4j_driver)
        except ServiceUnavailable as e:
            app.logger.critical(
                f"Neo4j connection failed: Service Unavailable. "
                f"Check URI, credentials, and network. Error: {e}",
                exc_info=True
            )
            raise ConnectionError("Failed to connect to Neo4j database.") from e
        except Exception as e:
            app.logger.critical(f"An unexpected error occurred during Neo4j driver initialization: {e}", exc_info=True)
            raise ConnectionError("Failed to initialize Neo4j database driver.") from e
    return neo4j_driver

def create_vector_indexes(driver):
    """
    Checks for and creates GDS vector indexes if they do not exist.
    """
    index_queries = {
        "file_index": """
            CREATE VECTOR INDEX `file_index` IF NOT EXISTS
            FOR (f:File) ON (f.embedding)
            OPTIONS {indexConfig: {
                `vector.dimensions`: 768,
                `vector.similarity_function`: 'cosine'
            }}
        """,
        "function_index": """
            CREATE VECTOR INDEX `function_index` IF NOT EXISTS
            FOR (func:Function) ON (func.embedding)
            OPTIONS {indexConfig: {
                `vector.dimensions`: 768,
                `vector.similarity_function`: 'cosine'
            }}
        """
    }
    try:
        with driver.session() as session:
            for index_name, query in index_queries.items():
                app.logger.info(f"Checking for GDS vector index: {index_name}")
                session.run(query)
                app.logger.info(f"GDS vector index '{index_name}' is ready.")
    except Neo4jError as e:
        app.logger.error(
            f"Failed to create or verify GDS vector index. "
            f"Please ensure the GDS plugin is installed in Neo4j. Error: {e}",
            exc_info=True
        )
        # Depending on the application's requirements, you might want to
        # raise an exception here to prevent the app from starting without the indexes.
        # For now, we'll log it as an error and continue.
    except Exception as e:
        app.logger.error(f"An unexpected error occurred during index creation: {e}", exc_info=True)

# --- Global Error Handlers ---
@app.errorhandler(400)
def handle_bad_request(e):
    app.logger.error(f"Bad Request (400): {e.description}", exc_info=True)
    return jsonify({
        "status": 400,
        "message": "Bad Request: " + getattr(e, 'description', 'Invalid request data.'),
        "error_type": "BadRequest"
    }), 400

@app.errorhandler(404)
def handle_not_found(e):
    app.logger.warning(f"Not Found (404): {request.path} was requested.", exc_info=True)
    return jsonify({
        "status": 404,
        "message": "Not Found: The requested resource does not exist.",
        "error_type": "NotFound"
    }), 404

@app.errorhandler(ConnectionError)
def handle_db_connection_error(e):
    app.logger.critical(f"Database connection error: {e}", exc_info=True)
    return jsonify({
        "status": 500,
        "message": "Internal Server Error: Could not connect to the database. Please try again later.",
        "error_type": "DatabaseConnectionError"
    }), 500

@app.errorhandler(GoogleAPIError)
def handle_google_api_error(e):
    app.logger.error(f"Google API Error: {e.reason} (Code: {e.code})", exc_info=True)
    return jsonify({
        "status": 500,
        "message": f"Internal Server Error: Google Cloud API issue. Reason: {e.reason}. Please check API permissions/quotas.",
        "error_type": "GoogleAPIError"
    }), 500

@app.errorhandler(Exception)
def handle_generic_error(e):
    # This is a catch-all for any unhandled exceptions
    app.logger.error(f"An unhandled internal server error occurred: {e}", exc_info=True)
    return jsonify({
        "status": 500,
        "message": "Internal Server Error: An unexpected error occurred. Please try again or contact support.",
        "error_type": "InternalServerError"
    }), 500


# --- Helper Functions ---
def generate_embeddings(text):
    """Generates embeddings for a given text using Vertex AI."""
    if not text:
        app.logger.warning("Attempted to generate embedding for empty text.")
        return []
    try:
        embeddings = embedding_model.get_embeddings([text])
        return embeddings[0].values
    except Exception as e:
        app.logger.error(f"Vertex AI embedding model error: {e}", exc_info=True)
        raise # Re-raise to be caught by the higher-level error handler

def retrieve_graph_context(query_embedding, user_query, session):
    """
    Retrieves relevant context from the Neo4j graph using vector search and Cypher queries.
    Enhanced with more sophisticated queries and better context extraction.
    """
    context = []
    
    try:
        # --- 1. Vector Search (Primary Method) ---
        # Use vector search to find relevant entities
        entity_query = """
        CALL db.index.vector.queryNodes('function_index', 5, $query_embedding) YIELD node, score
        WHERE score > 0.6 AND node.file_path IS NOT NULL
        RETURN node.name AS name, labels(node)[0] as type, node.file_path AS filePath, 
               node.description as description, score
        ORDER BY score DESC
        """
        app.logger.info("Executing entity vector search query...")
        entity_results = session.run(entity_query, query_embedding=query_embedding).data()
        
        for res in entity_results:
            entity_type = res.get('type', 'Entity')
            context.append(f"In file '{res['filePath']}', there is a {entity_type.lower()} called '{res['name']}'. {res['description']}")
        
        app.logger.info(f"Found {len(entity_results)} entity contexts via vector search.")
        
        # --- 2. Keyword Search (Complementary Method) ---
        # Extract keywords from the user query
        keywords = [word.lower() for word in user_query.split() if len(word) > 2]
        keywords = [word for word in keywords if word not in 
                   ['the', 'and', 'for', 'with', 'what', 'how', 'why', 'where', 'when', 'who', 'which']]
        
        if keywords:
            # Search for entities by name
            name_query = """
            MATCH (n)
            WHERE (ANY(keyword IN $keywords WHERE toLower(n.name) CONTAINS keyword))
            RETURN n.name as name, labels(n)[0] as type, n.file_path as filePath, 
                   n.description as description
            LIMIT 5
            """
            app.logger.info("Executing keyword name search...")
            name_results = session.run(name_query, keywords=keywords).data()
            
            for res in name_results:
                entity_type = res.get('type', 'Entity')
                context.append(f"Found a {entity_type.lower()} named '{res['name']}' in '{res['filePath']}' that matches your query. {res['description']}")
            
            # Search for entities by description
            desc_query = """
            MATCH (n)
            WHERE (ANY(keyword IN $keywords WHERE toLower(n.description) CONTAINS keyword))
            RETURN n.name as name, labels(n)[0] as type, n.file_path as filePath, 
                   n.description as description
            LIMIT 5
            """
            app.logger.info("Executing keyword description search...")
            desc_results = session.run(desc_query, keywords=keywords).data()
            
            for res in desc_results:
                entity_type = res.get('type', 'Entity')
                context.append(f"The {entity_type.lower()} '{res['name']}' in '{res['filePath']}' appears relevant to your question. {res['description']}")
        
        # --- 3. Relationship Exploration ---
        # If we found entities, explore their relationships
        if entity_results:
            top_entity = entity_results[0]
            entity_name = top_entity['name']
            entity_file = top_entity['filePath']
            
            # Find relationships for the top entity
            rel_query = """
            MATCH (n {name: $name, file_path: $filePath})-[r]->(m)
            RETURN n.name as source, type(r) as relationship, m.name as target, 
                   labels(m)[0] as targetType, r.context as context
            UNION
            MATCH (n)<-[r]-(m {name: $name, file_path: $filePath})
            RETURN m.name as source, type(r) as relationship, n.name as target, 
                   labels(n)[0] as targetType, r.context as context
            LIMIT 8
            """
            app.logger.info(f"Exploring relationships for entity: {entity_name}")
            rel_results = session.run(rel_query, name=entity_name, filePath=entity_file).data()
            
            for res in rel_results:
                rel_context = res.get('context', '')
                relationship = res['relationship'].lower().replace('_', ' ')
                if rel_context:
                    context.append(f"'{res['source']}' {relationship} '{res['target']}'. {rel_context}")
                else:
                    context.append(f"'{res['source']}' {relationship} '{res['target']}'.")
        
        # --- 4. File Context ---
        # Get information about the files containing the entities
        if entity_results:
            file_paths = list(set([res['filePath'] for res in entity_results if 'filePath' in res]))
            if file_paths:
                # Use a more comprehensive query to get file information
                file_query = """
                MATCH (f)
                WHERE (f:File OR f:SourceFile OR f:PythonModule OR f:JavaScriptModule OR f:CobolProgram 
                       OR f:SasProgram OR f:JclJob OR f:FlinkJob OR f:DataFile OR f:CppFile 
                       OR f:FortranProgram OR f:PliProgram OR f:AssemblyFile OR f:RpgProgram)
                AND f.path IN $filePaths
                RETURN f.path as path, f.repo_id as repoId, labels(f) as fileLabels
                """
                app.logger.info(f"Getting file context for {len(file_paths)} files")
                file_results = session.run(file_query, filePaths=file_paths).data()
                
                for res in file_results:
                    file_labels = res.get('fileLabels', [])
                    file_type = "file"
                    # Extract the most specific file type label (not 'File')
                    for label in file_labels:
                        if label != 'File':
                            file_type = label.replace('File', '').replace('Program', '').replace('Module', '').replace('Job', '')
                            break
                    
                    context.append(f"The {file_type.lower()} file '{res['path']}' is part of repository '{res.get('repoId', 'unknown')}'.")
                    
                    # Get other entities in the same file with improved query
                    file_entities_query = """
                    MATCH (f)-[:CONTAINS]->(e)
                    WHERE f.path = $path
                    RETURN e.name as name, labels(e)[0] as type
                    LIMIT 8
                    """
                    file_entities = session.run(file_entities_query, path=res['path']).data()
                    
                    if file_entities:
                        entities_info = []
                        for e in file_entities:
                            e_type = e.get('type', 'Entity').lower()
                            e_name = e.get('name', '')
                            if e_name:
                                entities_info.append(f"{e_type} '{e_name}'")
                                
                        if entities_info:
                            entities_str = ", ".join(entities_info)
                            context.append(f"The file '{res['path']}' contains: {entities_str}.")

    except Neo4jError as e:
        app.logger.error(f"Neo4j Cypher error during context retrieval: {e.message}", exc_info=True)
    except Exception as e:
        app.logger.error(f"An unexpected error occurred during context retrieval: {e}", exc_info=True)

    if not context:
        return "No specific context found in the graph."
    else:
        return "\n".join(context)

# --- API Endpoints ---
@app.route('/api/chat', methods=['POST'])
def chat_with_graph():
    app.logger.info("Received /api/chat request.")
    data = request.json
    user_query = data.get('query')
    conversation_history = data.get('history', [])

    if not user_query:
        app.logger.warning("Chat query received with no 'query' field.")
        return jsonify({"response": "Please provide a query."}), 400

    try:
        driver = get_neo4j_driver() # Ensure driver is connected
        app.logger.info(f"Generating embedding for user query: '{user_query[:50]}...'")
        query_embedding = generate_embeddings(user_query)

        if not query_embedding:
            app.logger.error("Failed to generate embedding for the query. Cannot proceed with RAG.")
            return jsonify({
                "response": "Could not generate embeddings for your query. Please try again.",
                "context_used": ""
            }), 500

        with driver.session() as session:
            app.logger.info("Retrieving graph context...")
            graph_context = retrieve_graph_context(query_embedding, user_query, session)
            app.logger.info(f"Graph context retrieved: {'Context found' if graph_context else 'No context found'}")

        # Format conversation history for the prompt
        conversation_context = ""
        if conversation_history:
            conversation_context = "Previous conversation:\n"
            for msg in conversation_history[-5:]:  # Only include the last 5 messages
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                conversation_context += f"{role.capitalize()}: {content}\n"
            
        prompt = f"""
        You are an AI assistant specialized in analyzing and explaining codebases based on a knowledge graph.
        Your task is to provide clear, accurate, and helpful information about code structure, functionality, and relationships in natural, conversational language.
        
        Important formatting guidelines:
        1. Respond in plain, conversational English - avoid bullet points and numbered lists unless absolutely necessary
        2. Format your response as a cohesive narrative rather than technical documentation
        3. Use paragraphs to organize information, not lists or technical outlines
        4. Write as if you're explaining to a fellow developer in a friendly conversation
        5. Focus on clarity and readability over technical formalism
        
        {conversation_context}
        
        User Question: {user_query}
        
        Context from Knowledge Graph:
        ---
        {graph_context}
        ---
        
        Based on this context, provide a clear, conversational, and technically accurate response that reads naturally.
        Use plain language and avoid overly structured formatting like bullet points or numbered lists.
        If you can't answer based on the provided context, acknowledge this limitation conversationally.
        """
        app.logger.info("Calling Generative Model (Gemini)...")
        response = generative_model.generate_content(prompt)
        app.logger.info("Gemini response received.")

        return jsonify({
            "response": response.text,
            "context_used": graph_context
        })

    except ConnectionError:
        # This will be caught by the @app.errorhandler(ConnectionError)
        app.logger.error("Chat API failed due to database connection issue.", exc_info=True)
        raise
    except GoogleAPIError:
        # This will be caught by the @app.errorhandler(GoogleAPIError)
        app.logger.error("Chat API failed due to Google API issue.", exc_info=True)
        raise
    except Exception as e:
        app.logger.error(f"An unexpected error occurred in /api/chat: {e}", exc_info=True)
        # This will be caught by the @app.errorhandler(Exception)
        raise

@app.route('/healthz', methods=['GET'])
def health_check():
    """
    Health check endpoint to verify the service is running and can connect to critical dependencies.
    """
    try:
        # Try to get Neo4j driver (will attempt connection if not already connected)
        driver = get_neo4j_driver()
        # Verify connectivity of the driver
        driver.verify_connectivity()
        app.logger.info("Health check: Neo4j connection OK.")

        # Try to make a dummy call to a Vertex AI model (e.g., embedding a small string)
        # This checks if the service account has permissions and API is accessible
        try:
            embedding_model.get_embeddings(["health check test"])
            app.logger.info("Health check: Vertex AI embeddings OK.")
        except Exception as ve:
            app.logger.error(f"Health check: Vertex AI embeddings FAILED: {ve}", exc_info=True)
            return jsonify({"status": "ERROR", "message": f"Vertex AI embeddings service unavailable: {ve}"}), 503

        # If both are successful
        return jsonify({"status": "OK", "message": "Service is healthy and connected to dependencies."}), 200
    except ConnectionError as e:
        app.logger.error(f"Health check: Neo4j connection FAILED: {e}", exc_info=True)
        return jsonify({"status": "ERROR", "message": f"Neo4j database connection failed: {e}"}), 503
    except Exception as e:
        app.logger.error(f"Health check: An unexpected error occurred during health check: {e}", exc_info=True)
        return jsonify({"status": "ERROR", "message": f"Unexpected health check error: {e}"}), 500

@app.route('/api/clear-database', methods=['POST'])
def clear_database():
    """
    Clear all data from the Neo4j database.
    This endpoint is used when a user wants to start fresh with a new codebase.
    """
    app.logger.info("Received request to clear the Neo4j database")
    
    try:
        driver = get_neo4j_driver()
        
        with driver.session() as session:
            # Delete all relationships first, then all nodes
            app.logger.info("Deleting all relationships in the database")
            session.run("MATCH ()-[r]-() DELETE r")
            
            app.logger.info("Deleting all nodes in the database")
            session.run("MATCH (n) DELETE n")
            
            app.logger.info("Database cleared successfully")
            
        return jsonify({
            "success": True,
            "message": "Database cleared successfully"
        })
        
    except ConnectionError:
        app.logger.error("Failed to clear database due to connection issue", exc_info=True)
        raise
    except Neo4jError as e:
        app.logger.error(f"Neo4j error while clearing database: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"Database error: {str(e)}"
        }), 500
    except Exception as e:
        app.logger.error(f"An unexpected error occurred while clearing database: {e}", exc_info=True)
        return jsonify({
            "success": False, 
            "message": f"Unexpected error: {str(e)}"
        }), 500

# --- Main Execution Block ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.logger.info(f"Starting Flask app on port {port}...")

    # For local testing, you must ensure all environment variables are set!
    # Example for Linux/macOS:
    # export GCP_PROJECT_ID="your-gcp-project-id"
    # export GCP_REGION="your-gcp-region"
    # export NEO4J_URI="neo4j+s://your-auradb-uri.databases.neo4j.io:7687"
    # export NEO4J_USERNAME="neo4j"
    # export NEO4J_PASSWORD="your_auradb_password"
    # python app.py

    # The app.run() for local development. In production, use gunicorn.
    app.run(host='0.0.0.0', port=port, debug=False) # Keep debug=False for more realistic error handling