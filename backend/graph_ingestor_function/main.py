import os
import json
import re
from google.cloud import storage
from neo4j import GraphDatabase
import vertexai
from vertexai.language_models import TextEmbeddingModel
from vertexai.generative_models import GenerativeModel

# Initialize clients (globally for better performance in Cloud Functions)
storage_client = storage.Client()
vertexai.init(project=os.environ.get('GCP_PROJECT_ID'), location=os.environ.get('GCP_REGION'))
embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")

# Neo4j AuraDB connection details (get these from Aura Console)
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Create a Neo4j driver instance (re-use across invocations if possible in CF)
# In Cloud Functions, a global driver is reused across "warm" invocations.
neo4j_driver = None
def get_neo4j_driver():
    global neo4j_driver
    if neo4j_driver is None:
        if not all([NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD]):
            raise ValueError("Neo4j credentials are not set in environment variables.")
        
        # Ensure we have proper strings for all connection parameters
        uri = str(NEO4J_URI) if NEO4J_URI is not None else ""
        username = str(NEO4J_USERNAME) if NEO4J_USERNAME is not None else ""
        password = str(NEO4J_PASSWORD) if NEO4J_PASSWORD is not None else ""
        
        if not uri or not username or not password:
            raise ValueError("Neo4j credentials cannot be empty.")
            
        neo4j_driver = GraphDatabase.driver(uri, auth=(username, password))
        # Optional: Verify connectivity on first creation
        neo4j_driver.verify_connectivity()
        print("Neo4j driver initialized and connected.")
    return neo4j_driver

def generate_embeddings(text):
    """Generates embeddings for a given text using Vertex AI."""
    try:
        embeddings = embedding_model.get_embeddings([text])
        return embeddings[0].values
    except Exception as e:
        print(f"Error generating embedding for text: '{text[:50]}...': {e}")
        return [] # Return empty list on failure

def ingest_data_to_neo4j(parsed_data, session):
    """
    Ingests parsed data from the enhanced CodeParser into Neo4j.
    Handles more detailed entity properties and relationships.
    """
    repo_id = parsed_data.get('repo_id')
    filename = parsed_data.get('filename')
    entities = parsed_data.get('entities', [])
    relationships = parsed_data.get('relationships', [])

    if not filename:
        print("Skipping ingestion: filename is missing from parsed data.")
        return

    # Determine file type based on extension
    file_extension = os.path.splitext(filename)[1].lower()
    
    # Classify file type
    file_type = "Module"
    if file_extension in ['.h', '.hpp', '.hxx']:
        file_type = "HeaderFile"
    elif file_extension in ['.c', '.cpp', '.cc', '.cxx']:
        file_type = "SourceFile"
    elif file_extension in ['.py']:
        file_type = "PythonModule"
    elif file_extension in ['.js', '.jsx', '.ts', '.tsx']:
        file_type = "JavaScriptModule"
    elif file_extension in ['.java']:
        file_type = "JavaClass"
    elif file_extension in ['.html', '.xml', '.json', '.yaml', '.yml']:
        file_type = "DataFile"
    
    # Create the File node with appropriate type
    file_name = os.path.basename(filename)
    session.run(
        f"MERGE (f:{file_type} {{path: $filename}}) SET f.repo_id = $repo_id, f.name = $file_name, f.extension = $extension",
        filename=filename, repo_id=repo_id, file_name=file_name, extension=file_extension
    )

    # Comprehensive mapping of entity types based on user requirements
    label_mapping = {
        # Basic code elements
        'function': 'Function',
        'method': 'Function',
        'variable': 'Variable',
        'struct': 'Struct',
        'record': 'Record',
        'type': 'Type',
        'module': 'Module',
        'file': 'Module',
        'class': 'Class',
        'object': 'Object',
        
        # Database related
        'database_table': 'DatabaseTable',
        'entity': 'Entity',
        
        # External interactions
        'external_api': 'ExternalAPI',
        'service': 'Service',
        
        # Business logic
        'business_rule': 'BusinessRule',
        'requirement': 'Requirement',
        
        # Control flow
        'loop': 'Loop',
        'branch': 'Branch',
        
        # I/O operations
        'input_operation': 'InputOperation',
        'output_operation': 'OutputOperation',
        'user_input': 'UserInput',
        
        # Execution units
        'job': 'Job',
        'script': 'Script',
        'program': 'Program',
        
        # Additional common types
        'constant': 'Constant',
        'interface': 'Interface',
        'import': 'Import',
        'paragraph': 'Paragraph',
        'enum': 'Enum',
        'define': 'Define'
    }

    # Ingest all entities with improved labeling and property handling
    for entity in entities:
        entity_name = entity.get('name')
        # Use the standardized entity_type field from the improved parser
        entity_type = entity.get('entity_type', 'Entity') 
        description = entity.get('description', '')
        
        # Ensure entity_type is a string before using lower()
        entity_type_str = str(entity_type).lower() if entity_type else 'entity'
        node_label = label_mapping.get(entity_type_str, entity_type_str.capitalize())
        
        # Ensure label is a valid identifier
        if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', node_label):
            node_label = 'Entity'

        # Generate embedding for the description
        embedding = generate_embeddings(description)
        
        # Extract properties from the enhanced parser output
        # The new parser puts additional properties in a nested 'properties' field
        properties = entity.get('properties', {})
        property_cypher = ""
        property_params = {
            'file_path': entity.get('file_path', filename),
            'name': entity_name,
            'description': description,
            'embedding': embedding
        }
        
        # Add enhanced properties to Neo4j
        for prop_key, prop_value in properties.items():
            # Skip null values and ensure property names are valid
            prop_key_str = str(prop_key)
            if prop_value is not None and re.match(r'^[A-Za-z][A-Za-z0-9_]*$', prop_key_str):
                # For array properties, convert to JSON string to store in Neo4j
                if isinstance(prop_value, (list, dict)):
                    prop_value = json.dumps(prop_value)
                property_cypher += f", e.{prop_key_str} = ${prop_key_str}"
                property_params[prop_key_str] = prop_value

        cypher = f"""
        MATCH (f:{file_type} {{path: $file_path}})
        MERGE (e:{node_label} {{name: $name, file_path: $file_path}})
        ON CREATE SET e.description = $description, e.embedding = $embedding{property_cypher}
        ON MATCH SET e.description = $description, e.embedding = $embedding{property_cypher}
        MERGE (f)-[:CONTAINS]->(e)
        """
        
        session.run(cypher, property_params)

    # Comprehensive mapping of relationship types based on user requirements
    rel_mapping = {
        # Function relationships
        'calls': 'CALLS',
        'returns': 'RETURNS',
        
        # Module relationships
        'defines': 'DEFINES',
        'includes': 'INCLUDES',
        'imports': 'IMPORTS',
        'depends_on': 'DEPENDS_ON',
        
        # Variable relationships
        'declares': 'DECLARES',
        'uses': 'USES',
        'assigns': 'ASSIGNS',
        
        # I/O relationships
        'reads_from': 'READS_FROM',
        'writes_to': 'WRITES_TO',
        'interacts_with': 'INTERACTS_WITH',
        'logs_to': 'LOGS_TO',
        
        # Type relationships
        'composes': 'COMPOSES',
        'contains': 'CONTAINS',
        
        # OOP relationships
        'extends': 'EXTENDS',
        'inherits': 'INHERITS_FROM',
        
        # Execution relationships
        'executes': 'EXECUTES',
        'calls_with_input_from': 'CALLS_WITH_INPUT_FROM',
        'satisfies': 'SATISFIES',
        'triggered_by': 'TRIGGERED_BY',
        
        # Control flow relationships
        'controls_flow_to': 'CONTROLS_FLOW_TO',
        
        # Concurrency relationships
        'spawns': 'SPAWNS',
        
        # Memory management
        'allocates': 'ALLOCATES',
        'deallocates': 'DEALLOCATES',
        
        # Legacy relationships for backward compatibility
        'implements': 'IMPLEMENTS',
        'overrides': 'OVERRIDES'
    }

    # Ingest all relationships with improved type handling
    for rel in relationships:
        source_name = rel.get('source')
        target_name = rel.get('target')
        # Use the standardized relationship_type field from the improved parser
        rel_type = rel.get('relationship_type', 'RELATED_TO')
        
        # Ensure rel_type is a string before using lower()
        rel_type_str = str(rel_type).lower() if rel_type else 'related_to'
        rel_type_upper = rel_mapping.get(rel_type_str, rel_type_str).upper()
        
        # Sanitize rel_type to prevent Cypher injection
        sanitized_rel_type = re.sub(r'[^A-Z_]', '', rel_type_upper)

        if not all([source_name, target_name, sanitized_rel_type]):
            continue

        # More sophisticated relationship creation with better matching
        cypher = f"""
        MATCH (source {{name: $source_name, file_path: $filename}})
        MATCH (target {{name: $target_name, file_path: $filename}})
        MERGE (source)-[r:{sanitized_rel_type}]->(target)
        SET r.context = $context
        """
        
        session.run(cypher, {
            'source_name': source_name,
            'target_name': target_name,
            'filename': filename,
            'context': rel.get('context', '')
        })
        
        # If we couldn't find the exact match, try a more flexible approach for cross-file relationships
        # This is useful for dependencies between files
        result = session.run(
            f"""
            MATCH (source {{name: $source_name}}), (target {{name: $target_name}})
            WHERE source.file_path <> target.file_path
            RETURN count(*) as count
            """, 
            {'source_name': source_name, 'target_name': target_name}
        ).single()
        
        if result and result["count"] > 0:
            session.run(
                f"""
                MATCH (source {{name: $source_name}}), (target {{name: $target_name}})
                WHERE source.file_path <> target.file_path
                MERGE (source)-[r:{sanitized_rel_type}]->(target)
                SET r.context = $context, r.cross_file = true
                """,
                {
                    'source_name': source_name,
                    'target_name': target_name,
                    'context': rel.get('context', '') + " (cross-file relationship)"
                }
            )

    print(f"Ingested data for {filename} into Neo4j with enhanced entity and relationship handling.")


def graph_ingestor_entrypoint(event, context):
    """
    Cloud Function entry point for graph ingestion.
    Triggered by new parsed data uploads to the parsed data bucket.
    """
    bucket_name = event['bucket']
    file_name = event['name']

    print(f"Processing parsed file: {file_name} from bucket: {bucket_name}")

    if not file_name.endswith('.json'):
        print(f"Skipping non-JSON file: {file_name}")
        return

    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        parsed_data_content = blob.download_as_text()
        parsed_data = json.loads(parsed_data_content)

        driver = get_neo4j_driver()
        with driver.session() as session:
            ingest_data_to_neo4j(parsed_data, session)

    except Exception as e:
        print(f"Error ingesting {file_name}: {e}")
        # Log the error for debugging in Cloud Logging
        raise # Re-raise to indicate function failure