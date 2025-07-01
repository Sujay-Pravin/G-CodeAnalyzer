import os
import shutil
import tempfile
import time
import threading
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import storage
from git import Repo, GitCommandError # Using GitPython
import stat # Keep this for Windows cleanup
from neo4j import GraphDatabase

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Initialize Google Cloud Storage client
storage_client = storage.Client()
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'your-legacy-code-bucket') # Set this env var or use a default

# REMOVE THESE LINES:
# import vertexai
# from vertexai.language_models import TextEmbeddingModel
# from vertexai.generative_models import GenerativeModel
# vertexai.init(
#     project=os.environ.get("GCP_PROJECT_ID"),
#     location=os.environ.get("GCP_REGION")
# )
# embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
# generative_model = GenerativeModel("gemini-1.5-flash-001")


# In-memory store to map cloned repos to temp paths (for multi-step process)
# In a real app, this should be persisted (e.g., in a database or Redis)
# For hackathon, we'll use a simple dict keyed by repo_id (e.g., original GitHub URL hash)
CLONED_REPOS = {}

# Dict to track processing progress
PROCESSING_STATUS = {}

def list_files_in_directory(path):
    """Recursively lists all files in a directory."""
    file_list = []
    for root, _, files in os.walk(path):
        for file in files:
            # Get path relative to the initial clone directory
            relative_path = os.path.relpath(os.path.join(root, file), path)
            file_list.append(relative_path)
    return file_list

def remove_readonly(func, path, excinfo):
    # Clear the readonly bit and reattempt the removal
    os.chmod(path, stat.S_IWRITE)
    func(path)

def process_files_in_batches(repo_id, files_to_process, temp_repo_path):
    """Process files in batches of 2 at a time"""
    try:
        # Update status
        PROCESSING_STATUS[repo_id] = {
            "total_files": len(files_to_process),
            "processed": 0,
            "current_file": "",
            "status": "processing",
            "message": "Starting file processing"
        }

        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        batch_size = 2
        total_processed = 0
        uploaded_files = []

        # Process in batches
        for i in range(0, len(files_to_process), batch_size):
            batch = files_to_process[i:i+batch_size]
            
            for file_path in batch:
                local_file_path = os.path.join(temp_repo_path, file_path)
                if os.path.exists(local_file_path):
                    # Update status
                    PROCESSING_STATUS[repo_id]["current_file"] = file_path
                    PROCESSING_STATUS[repo_id]["message"] = f"Processing {file_path}"

                    # Define GCS destination path
                    destination_blob_name = f'cloned_repos/{repo_id}/{file_path}'
                    blob = bucket.blob(destination_blob_name)
                    blob.upload_from_filename(local_file_path)
                    uploaded_files.append(file_path)
                    
                    # Update counters
                    total_processed += 1
                    PROCESSING_STATUS[repo_id]["processed"] = total_processed
                    
                    print(f"Uploaded {local_file_path} to gs://{GCS_BUCKET_NAME}/{destination_blob_name}")
            
            # Wait a bit for the cloud function to process this batch
            PROCESSING_STATUS[repo_id]["message"] = f"Waiting for batch processing to complete ({total_processed}/{len(files_to_process)})"
            time.sleep(3)  # Give cloud functions time to process

        # Step 3: Wait for all processing to complete
        PROCESSING_STATUS[repo_id]["message"] = "Waiting for Neo4j ingestion to complete"
        wait_for_neo4j_processing(repo_id, uploaded_files)

        # Clean up
        try:
            shutil.rmtree(temp_repo_path, onerror=remove_readonly)
            if repo_id in CLONED_REPOS:
                del CLONED_REPOS[repo_id]
            print(f"Cleaned up temp directory: {temp_repo_path}")
        except Exception as e:
            print(f"Error during cleanup: {e}")

    except Exception as e:
        PROCESSING_STATUS[repo_id] = {
            "status": "error",
            "message": f"Error processing files: {str(e)}"
        }
        print(f"Error in batch processing thread: {e}")

def wait_for_neo4j_processing(repo_id, uploaded_files):
    """Wait for Neo4j to finish processing all files"""
    try:
        # Get Neo4j connection details
        neo4j_uri = os.getenv("NEO4J_URI", "")
        neo4j_username = os.getenv("NEO4J_USERNAME", "")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "")
        
        if not neo4j_uri or not neo4j_username or not neo4j_password:
            PROCESSING_STATUS[repo_id]["status"] = "error"
            PROCESSING_STATUS[repo_id]["message"] = "Neo4j connection details missing"
            return
        
        # Connect to Neo4j
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
        
        # Maximum wait time (2 minutes)
        max_wait_time = 120  # seconds
        start_time = time.time()
        all_processed = False
        files_found = 0
        
        # Poll Neo4j to check if processing is complete
        while time.time() - start_time < max_wait_time:
            try:
                with driver.session() as session:
                    # Check if all file nodes exist in Neo4j
                    files_found = 0
                    for file_path in uploaded_files:
                        file_name = os.path.basename(file_path)
                        # Query to check if the file node exists
                        result = session.run(
                            """
                            MATCH (f) 
                            WHERE f.name = $file_name OR f.path CONTAINS $file_path
                            RETURN count(f) as node_count
                            """,
                            {"file_name": file_name, "file_path": file_path}
                        ).single()
                        
                        if result and result["node_count"] > 0:
                            files_found += 1
                    
                    # Update progress
                    PROCESSING_STATUS[repo_id]["message"] = f"Found {files_found}/{len(uploaded_files)} files in Neo4j"
                    
                    if files_found == len(uploaded_files):
                        # All nodes are present, create a consolidated graph
                        PROCESSING_STATUS[repo_id]["message"] = "Creating graph visualization"
                        session.run(
                            """
                            MATCH (n)
                            WITH collect(n) AS nodes
                            CALL apoc.graph.fromCypher("MATCH (n) RETURN n", {}, "graph", null)
                            YIELD graph
                            RETURN graph
                            """
                        )
                        all_processed = True
                        break
            
            except Exception as e:
                PROCESSING_STATUS[repo_id]["message"] = f"Error checking Neo4j: {str(e)}"
                print(f"Error checking Neo4j: {e}")
            
            # Wait a bit before checking again
            time.sleep(3)
        
        # Close the driver
        driver.close()
        
        if all_processed:
            PROCESSING_STATUS[repo_id]["status"] = "complete"
            PROCESSING_STATUS[repo_id]["message"] = "Processing complete. All files loaded into Neo4j."
        else:
            PROCESSING_STATUS[repo_id]["status"] = "incomplete"
            PROCESSING_STATUS[repo_id]["message"] = f"Timeout waiting for processing. Found {files_found}/{len(uploaded_files)} files in Neo4j."
    
    except Exception as e:
        PROCESSING_STATUS[repo_id]["status"] = "error"
        PROCESSING_STATUS[repo_id]["message"] = f"Error during Neo4j processing: {str(e)}"
        print(f"Error in Neo4j processing: {e}")

@app.route('/api/fetch-repo-files', methods=['POST'])
def fetch_repo_files():
    data = request.json
    github_url = data.get('github_url')

    if not github_url:
        return jsonify({"success": False, "message": "GitHub URL is required."}), 400

    if not github_url.startswith('https://github.com/'):
        return jsonify({"success": False, "message": "Invalid GitHub URL format. Must start with https://github.com/"}), 400

    temp_dir = None # Initialize temp_dir outside try to ensure it's defined for cleanup
    repo_id = None # Initialize repo_id

    try:
        # Create a unique ID for this repo cloning session
        import hashlib
        repo_id = hashlib.sha256(github_url.encode()).hexdigest()

        # Create a temporary directory for cloning
        temp_dir = tempfile.mkdtemp()
        CLONED_REPOS[repo_id] = temp_dir # Store the temp path

        print(f"Cloning {github_url} into {temp_dir}")
        Repo.clone_from(github_url, temp_dir) # Use GitPython to clone
        print(f"Cloned successfully: {github_url}")

        # List all files in the cloned repository
        files = list_files_in_directory(temp_dir)

        return jsonify({
            "success": True,
            "message": "Repository cloned successfully. Select files.",
            "files": files,
            "repo_id": repo_id # Send repo_id back to frontend
        })

    except GitCommandError as e:
        print(f"Git cloning error: {e}")
        # Clean up temp directory if cloning failed
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, onerror=remove_readonly)
            if repo_id in CLONED_REPOS:
                del CLONED_REPOS[repo_id]
        return jsonify({"success": False, "message": f"Failed to clone repository: {str(e)}"}), 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, onerror=remove_readonly)
            if repo_id in CLONED_REPOS:
                del CLONED_REPOS[repo_id]
        return jsonify({"success": False, "message": f"An error occurred: {str(e)}"}), 500

@app.route('/api/process-files', methods=['POST'])
def process_selected_files():
    data = request.json
    selected_files = data.get('selected_files')
    repo_id = data.get('repo_id') # Get repo_id from frontend

    if not selected_files or not repo_id:
        return jsonify({"success": False, "message": "Selected files and repo ID are required."}), 400

    temp_repo_path = CLONED_REPOS.get(repo_id)
    if not temp_repo_path or not os.path.exists(temp_repo_path):
        return jsonify({"success": False, "message": "Repository not found or session expired. Please re-clone."}), 404

    try:
        # Initialize the status for this repo
        PROCESSING_STATUS[repo_id] = {
            "total_files": len(selected_files),
            "processed": 0,
            "current_file": "",
            "status": "starting",
            "message": "Processing starting"
        }
        
        # Start a background thread to process files in batches
        processing_thread = threading.Thread(
            target=process_files_in_batches,
            args=(repo_id, selected_files, temp_repo_path)
        )
        processing_thread.daemon = True
        processing_thread.start()
        
        return jsonify({
            "success": True,
            "message": "File processing started. Check progress with the /api/processing-status endpoint.",
            "total_files": len(selected_files),
            "repo_id": repo_id
        })

    except Exception as e:
        print(f"Error starting file processing: {e}")
        return jsonify({"success": False, "message": f"Failed to start processing: {str(e)}"}), 500

@app.route('/api/processing-status', methods=['GET'])
def check_processing_status():
    """Endpoint to check processing status"""
    repo_id = request.args.get('repo_id')
    
    if not repo_id:
        return jsonify({"success": False, "message": "repo_id is required"}), 400
        
    if repo_id not in PROCESSING_STATUS:
        return jsonify({"success": False, "message": "No processing status found for this repo"}), 404
        
    return jsonify({
        "success": True,
        "repo_id": repo_id,
        "status": PROCESSING_STATUS[repo_id]
    })

# Basic Flask run setup for local development
if __name__ == '__main__':
    # Ensure a default GCS bucket name for local testing if not set in env
    if not os.getenv('GCS_BUCKET_NAME'):
        os.environ['GCS_BUCKET_NAME'] = 'my-legacy-code-bucket' # CHANGE THIS TO YOUR ACTUAL BUCKET NAME

    # For local testing, ensure your gcloud application-default login is done
    # gcloud auth application-default login
    app.run(debug=True, port=5000) # Run Flask on port 5000