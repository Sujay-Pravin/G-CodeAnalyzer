import os
import shutil
import tempfile
import time
import threading
import json
import requests
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
    for root, dirs, files in os.walk(path):
        # Skip .git directories
        if '.git' in dirs:
            dirs.remove('.git')
            
        # Skip any other hidden directories starting with dot
        dirs[:] = [d for d in dirs if not d.startswith('.')]
            
        for file in files:
            # Skip files that start with .git or any hidden files
            if file.startswith('.git') or file.startswith('.'):
                continue
                
            # Get path relative to the initial clone directory
            relative_path = os.path.relpath(os.path.join(root, file), path)
            file_list.append(relative_path)
    return file_list

def remove_readonly(func, path, excinfo):
    # Clear the readonly bit and reattempt the removal
    os.chmod(path, stat.S_IWRITE)
    func(path)

def process_files_in_batches(repo_id, files_to_process, temp_repo_path):
    """Process files in batches"""
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
        batch_size = 5  # Increased from 2 to 5
        total_processed = 0
        uploaded_files = []
        failed_files = []

        # Process in batches
        for i in range(0, len(files_to_process), batch_size):
            batch = files_to_process[i:i+batch_size]
            batch_uploaded = []
            
            for file_path in batch:
                try:
                    local_file_path = os.path.join(temp_repo_path, file_path)
                    if os.path.exists(local_file_path):
                        # Update status
                        PROCESSING_STATUS[repo_id]["current_file"] = file_path
                        PROCESSING_STATUS[repo_id]["message"] = f"Processing {file_path}"

                        # Define GCS destination path
                        destination_blob_name = f'cloned_repos/{repo_id}/{file_path}'
                        blob = bucket.blob(destination_blob_name)
                        
                        # Add repo_id metadata to help with identification
                        metadata = {
                            "repo_id": repo_id,
                            "file_path": file_path,
                            "file_name": os.path.basename(file_path)
                        }
                        blob.metadata = metadata
                        
                        blob.upload_from_filename(local_file_path)
                        uploaded_files.append(file_path)
                        batch_uploaded.append(file_path)
                        
                        # Update counters
                        total_processed += 1
                        PROCESSING_STATUS[repo_id]["processed"] = total_processed
                        
                        print(f"Uploaded {local_file_path} to gs://{GCS_BUCKET_NAME}/{destination_blob_name} with metadata: {metadata}")
                    else:
                        print(f"File not found: {local_file_path}")
                        failed_files.append(file_path)
                except Exception as e:
                    print(f"Error processing file {file_path}: {e}")
                    failed_files.append(file_path)
                    # Continue with the next file
            
            # Wait longer for each batch to be processed before moving to the next batch
            if batch_uploaded:
                PROCESSING_STATUS[repo_id]["message"] = f"Waiting for batch processing to complete ({total_processed}/{len(files_to_process)})"
                time.sleep(10)  # Increased from 3 to 10 seconds
                
                # Double check if files in this batch were processed before moving on
                if repo_id in PROCESSING_STATUS and PROCESSING_STATUS[repo_id] is not None and "status" in PROCESSING_STATUS[repo_id] and PROCESSING_STATUS[repo_id]["status"] != "error":
                    PROCESSING_STATUS[repo_id]["message"] = f"Checking if batch was processed in Neo4j"
                    verify_batch_in_neo4j(repo_id, batch_uploaded)

        # Record any failed files
        if failed_files:
            PROCESSING_STATUS[repo_id]["failed_files"] = failed_files
            print(f"Failed to process {len(failed_files)} files: {failed_files}")

        # Step 3: Wait for all processing to complete
        if uploaded_files:
            PROCESSING_STATUS[repo_id]["message"] = "Waiting for Neo4j ingestion to complete"
            wait_for_neo4j_processing(repo_id, uploaded_files)
        else:
            PROCESSING_STATUS[repo_id]["status"] = "error"
            PROCESSING_STATUS[repo_id]["message"] = "No files were successfully uploaded"

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

def verify_batch_in_neo4j(repo_id, batch_files):
    """Verify if a batch of files has been processed in Neo4j"""
    try:
        # Get Neo4j connection details
        neo4j_uri = os.getenv("NEO4J_URI", "")
        neo4j_username = os.getenv("NEO4J_USERNAME", "")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "")
        
        if not neo4j_uri or not neo4j_username or not neo4j_password:
            print("Neo4j connection details missing, skipping batch verification")
            return
        
        # Connect to Neo4j
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
        
        # Maximum wait time (30 seconds)
        max_wait_time = 30
        start_time = time.time()
        batch_processed = False
        
        file_names = [os.path.basename(file_path) for file_path in batch_files]
        print(f"Verifying batch of {len(batch_files)} files in Neo4j: {file_names}")
        
        # Poll Neo4j to check if processing is complete for this batch
        while time.time() - start_time < max_wait_time:
            try:
                with driver.session() as session:
                    # Check for each specific file in the batch
                    files_found = 0
                    
                    for file_path in batch_files:
                        file_name = os.path.basename(file_path)
                        
                        # Query to check if the file exists
                        result = session.run(
                            """
                            MATCH (f) 
                            WHERE (f.name = $file_name OR f.filename = $file_name 
                                  OR f.path CONTAINS $file_path OR f.filepath = $file_path
                                  OR f.original_path = $file_path)
                            AND (f.repo_id = $repo_id OR f.repo_id IS NULL)
                            RETURN count(f) as node_count
                            """,
                            {"file_name": file_name, "file_path": file_path, "repo_id": repo_id}
                        ).single()
                        
                        if result and result["node_count"] > 0:
                            files_found += 1
                    
                    if files_found > 0:
                        print(f"Verified {files_found}/{len(batch_files)} files in this batch are in Neo4j")
                        batch_processed = True
                        break
                    
            except Exception as e:
                print(f"Error verifying batch in Neo4j: {e}")
            
            # Wait 2 seconds before checking again
            time.sleep(2)
        
        # Close the driver
        driver.close()
        
        if not batch_processed:
            print(f"Warning: Batch verification timed out, continuing anyway")
    
    except Exception as e:
        print(f"Error in batch verification: {e}")
        # Continue processing even if verification fails

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
        
        # Maximum wait time (5 minutes) - increased for large file sets
        max_wait_time = 300  # seconds (increased from 180 to 300)
        start_time = time.time()
        all_processed = False
        files_found = 0
        
        # Collect file names for proper matching
        file_names = [os.path.basename(file_path) for file_path in uploaded_files]
        file_paths = uploaded_files
        
        print(f"Final verification for {len(uploaded_files)} files in Neo4j: {file_names}")
        
        # Track consecutive polls with same file count to detect stalls
        last_files_found = -1
        stall_count = 0
        max_stall_count = 5  # Consider processing stalled after 5 consecutive identical polls
        
        # Poll Neo4j to check if processing is complete
        while time.time() - start_time < max_wait_time:
            try:
                with driver.session() as session:
                    # First, check how many total file nodes exist for this repo
                    repo_check = session.run(
                        """
                        MATCH (f)
                        WHERE f.repo_id = $repo_id
                        RETURN count(f) as total_nodes
                        """,
                        {"repo_id": repo_id}
                    ).single()
                    
                    total_nodes_in_db = repo_check["total_nodes"] if repo_check else 0
                    print(f"Found {total_nodes_in_db} total nodes for repo_id {repo_id}")
                    
                    # Next, check for each specific file - using multiple approaches for better matching
                    files_found = 0
                    found_files = []
                    missing_files = []
                    
                    # Try alternative approach to find file nodes - with more flexible matching
                    alt_check = session.run(
                        """
                        MATCH (f)
                        WHERE f.repo_id = $repo_id OR f.repo_id IS NULL
                        RETURN f.name as name, f.path as path, f.filepath as filepath, f.filename as filename
                        """,
                        {"repo_id": repo_id}
                    ).data()
                    
                    # Create a lookup dictionary of all possible node identifiers
                    node_lookups = {}
                    for node in alt_check:
                        # Add all possible identifiers to the lookup
                        if node and "name" in node and node["name"]:
                            node_lookups[node["name"].lower()] = True
                        if node and "path" in node and node["path"]:
                            node_lookups[node["path"].lower()] = True
                            node_lookups[os.path.basename(node["path"]).lower()] = True
                        if node and "filepath" in node and node["filepath"]:
                            node_lookups[node["filepath"].lower()] = True
                            node_lookups[os.path.basename(node["filepath"]).lower()] = True
                        if node and "filename" in node and node["filename"]:
                            node_lookups[node["filename"].lower()] = True
                    
                    # Check each uploaded file against the lookup dictionary
                    for i, file_path in enumerate(uploaded_files):
                        file_name = file_names[i]
                        file_found = False
                        
                        # Check file in multiple ways
                        if file_name.lower() in node_lookups:
                            file_found = True
                        elif file_path.lower() in node_lookups:
                            file_found = True
                        elif file_path.replace('\\', '/').lower() in node_lookups:
                            file_found = True
                        
                        # Traditional query approach as fallback
                        if not file_found:
                            # Standard query to check if the file node exists
                            result = session.run(
                                """
                                MATCH (f) 
                                WHERE (f.name = $file_name OR f.filename = $file_name 
                                      OR f.path CONTAINS $file_path OR f.filepath = $file_path
                                      OR f.original_path = $file_path)
                                AND (f.repo_id = $repo_id OR f.repo_id IS NULL)
                                RETURN f.name, f.path, count(f) as node_count
                                """,
                                {"file_name": file_name, "file_path": file_path, "repo_id": repo_id}
                            ).single()
                            
                            if result and result["node_count"] > 0:
                                file_found = True
                        
                        # Record results
                        if file_found:
                            files_found += 1
                            found_files.append(file_name)
                            print(f"Found file in Neo4j: {file_name} ({files_found}/{len(uploaded_files)})")
                        else:
                            missing_files.append(file_name)
                            print(f"File not found in Neo4j yet: {file_name}")
                    
                    # Update progress
                    PROCESSING_STATUS[repo_id]["message"] = f"Found {files_found}/{len(uploaded_files)} files in Neo4j"
                    
                    # Check for stalled processing
                    if files_found == last_files_found:
                        stall_count += 1
                    else:
                        stall_count = 0
                        last_files_found = files_found
                    
                    if stall_count >= max_stall_count:
                        print(f"Processing appears stalled at {files_found}/{len(uploaded_files)} files for {stall_count} consecutive checks")
                        # If we've processed at least 50% of files, consider it partial success
                        if files_found >= len(uploaded_files) * 0.5:
                            print(f"Considering as partial success with {files_found}/{len(uploaded_files)} files")
                            all_processed = True
                            break
                    
                    if found_files:
                        print(f"Found files: {found_files}")
                    if missing_files:
                        print(f"Missing files: {missing_files}")
                    
                    # Consider processing complete in these cases:
                    # 1. All files are found
                    # 2. We have more nodes than files (likely some files created multiple nodes)
                    # 3. We have at least 75% of files and it's been at least 2 minutes
                    time_elapsed = time.time() - start_time
                    percent_found = files_found / len(uploaded_files) if uploaded_files else 0
                    
                    if files_found == len(uploaded_files):
                        # All files found - complete success
                        all_processed = True
                        break
                    elif total_nodes_in_db >= len(uploaded_files) * 1.5:
                        # More nodes than files - likely success with multiple nodes per file
                        print(f"Found {total_nodes_in_db} nodes for {len(uploaded_files)} files - considering complete")
                        all_processed = True
                        break
                    elif percent_found >= 0.75 and time_elapsed > 120:
                        # 75% of files found after 2 minutes - partial success
                        print(f"Found {percent_found*100:.1f}% of files after {time_elapsed:.1f} seconds - considering partial success")
                        all_processed = True
                        break
            
            except Exception as e:
                PROCESSING_STATUS[repo_id]["message"] = f"Error checking Neo4j: {str(e)}"
                print(f"Error checking Neo4j: {e}")
            
            # Wait longer between checks (8 seconds)
            time.sleep(8)
        
        # Close the driver
        driver.close()
        
        if all_processed:
            # If all files were found, mark as complete
            if files_found == len(uploaded_files):
                PROCESSING_STATUS[repo_id]["status"] = "complete"
                PROCESSING_STATUS[repo_id]["message"] = f"Processing complete. All {files_found} files loaded into Neo4j."
            else:
                # Otherwise, mark as partial success
                PROCESSING_STATUS[repo_id]["status"] = "partial"
                PROCESSING_STATUS[repo_id]["message"] = f"Partial processing complete. Found {files_found}/{len(uploaded_files)} files in Neo4j."
                
            # Create graph visualization
            try:
                print("Creating graph visualization")
                # Connect to Neo4j again for visualization
                driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
                with driver.session() as session:
                    session.run(
                        """
                        MATCH (n)
                        WHERE n.repo_id = $repo_id OR n.repo_id IS NULL
                        WITH collect(n) AS nodes
                        CALL apoc.graph.fromCypher("MATCH (n) WHERE n.repo_id = $repo_id OR n.repo_id IS NULL RETURN n", 
                                                  {repo_id: $repo_id}, "graph", null)
                        YIELD graph
                        RETURN graph
                        """,
                        {"repo_id": repo_id}
                    )
                driver.close()
            except Exception as e:
                print(f"Error creating graph visualization: {e}")
        else:
            # If we found any files, still consider it a partial success
            if files_found > 0:
                PROCESSING_STATUS[repo_id]["status"] = "partial"
                PROCESSING_STATUS[repo_id]["message"] = f"Partial processing complete. Found {files_found}/{len(uploaded_files)} files in Neo4j."
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
        # First, clear the Neo4j database
        try:
            # Get RAG API URL from environment variable or default to localhost:5001
            rag_api_url = os.getenv("RAG_API_URL", "http://localhost:5001")
            clear_db_url = f"{rag_api_url}/api/clear-database"
            
            response = requests.post(clear_db_url, timeout=30)
            
            if response.status_code == 200:
                print("Successfully cleared Neo4j database before processing new repository")
            else:
                print(f"Warning: Failed to clear Neo4j database. Status code: {response.status_code}")
        except Exception as e:
            print(f"Warning: Error clearing Neo4j database: {e}. Continuing with repository cloning.")
            # We continue even if clearing fails
        
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
        # Initialize processing status for this repo_id
        PROCESSING_STATUS[repo_id] = {
            "status": "starting",
            "message": "Starting file processing",
            "total_files": len(selected_files),
            "processed": 0
        }
        
        # Start file processing in a separate thread
        thread = threading.Thread(
            target=process_files_in_batches,
            args=(repo_id, selected_files, temp_repo_path)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "File processing started",
            "repo_id": repo_id
        })
        
    except Exception as e:
        PROCESSING_STATUS[repo_id] = {
            "status": "error",
            "message": f"Error starting processing: {str(e)}"
        }
        return jsonify({"success": False, "message": f"An error occurred: {str(e)}"}), 500

@app.route('/api/processing-status', methods=['GET'])
def check_processing_status():
    repo_id = request.args.get('repo_id')
    if not repo_id:
        return jsonify({"success": False, "message": "Repository ID is required."}), 400
    
    if repo_id not in PROCESSING_STATUS:
        return jsonify({
            "success": False,
            "message": "No processing status found for this repository."
        }), 404
    
    status = PROCESSING_STATUS[repo_id]
    
    # Check if processing is complete or partial success
    is_complete = status.get("status") == "complete"
    is_partial = status.get("status") == "partial"
    
    # Return a success response for both complete and partial success
    if is_complete or is_partial:
        response = {
            "success": True,
            "status": status.get("status", "unknown"),
            "message": status.get("message", "Processing status unavailable"),
            "is_complete": is_complete or is_partial,  # Consider partial as complete for UI purposes
            "files_processed": status.get("processed", 0),
            "total_files": status.get("total_files", 0)
        }
        
        # Add information about partial processing if relevant
        if is_partial:
            response["partial_success"] = True
            response["warning"] = "Some files could not be processed. You can still proceed to the chat interface."
            if "failed_files" in status:
                response["failed_files"] = status["failed_files"]
                
        return jsonify(response)
    
    # Otherwise, return the current status
    return jsonify({
        "success": True,
        "status": status.get("status", "unknown"),
        "message": status.get("message", "Processing status unavailable"),
        "is_complete": False,
        "files_processed": status.get("processed", 0),
        "total_files": status.get("total_files", 0)
    })

@app.route('/api/get-file-content', methods=['POST'])
def get_file_content():
    """Fetch the content of a specific file from a cloned repository"""
    try:
        data = request.get_json()
        repo_id = data.get('repo_id')
        file_path = data.get('file_path')
        
        if not repo_id or not file_path:
            return jsonify({
                'success': False,
                'message': 'Missing repo_id or file_path parameter'
            }), 400
            
        # Check if repository exists in our cloned repos
        if repo_id not in CLONED_REPOS:
            return jsonify({
                'success': False,
                'message': 'Repository not found. It may have been cleaned up or never cloned.'
            }), 404
            
        temp_repo_path = CLONED_REPOS[repo_id]
        full_file_path = os.path.join(temp_repo_path, file_path)
        
        if not os.path.exists(full_file_path):
            return jsonify({
                'success': False,
                'message': f'File not found: {file_path}'
            }), 404
            
        # Read file content
        try:
            with open(full_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            return jsonify({
                'success': True,
                'content': content,
                'file_path': file_path
            })
        except UnicodeDecodeError:
            # If the file is binary, return an error
            return jsonify({
                'success': False,
                'message': 'File appears to be binary and cannot be displayed'
            }), 415
        
    except Exception as e:
        print(f"Error getting file content: {e}")
        return jsonify({
            'success': False,
            'message': f'Error retrieving file content: {str(e)}'
        }), 500

# Basic Flask run setup for local development
if __name__ == '__main__':
    # Ensure a default GCS bucket name for local testing if not set in env
    if not os.getenv('GCS_BUCKET_NAME'):
        os.environ['GCS_BUCKET_NAME'] = 'my-legacy-code-bucket' # CHANGE THIS TO YOUR ACTUAL BUCKET NAME

    # For local testing, ensure your gcloud application-default login is done
    # gcloud auth application-default login
    app.run(debug=True, port=5000) # Run Flask on port 5000