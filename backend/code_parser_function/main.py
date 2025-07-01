import functions_framework
import logging
import os
from google.cloud import storage
import json
from typing import List, Tuple, Dict, Any
import re
from vertexai.generative_models import GenerativeModel
import vertexai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Data Classes for Code Structure ---

class CodeEntity:
    def __init__(self, name: str, entity_type: str, file_path: str, description: str = "", properties: Dict[str, Any] = None):
        self.name = name
        self.entity_type = entity_type
        self.file_path = file_path
        self.description = description
        self.properties = properties if properties is not None else {}
    
    def to_dict(self):
        result = self.__dict__.copy()
        # Only include properties if they exist and aren't empty
        if not self.properties:
            del result['properties']
        return result

class CodeRelationship:
    def __init__(self, source: str, target: str, relationship_type: str, context: str = ""):
        self.source = source
        self.target = target
        self.relationship_type = relationship_type
        self.context = context

    def to_dict(self):
        return self.__dict__

# --- The Core Parsing Logic ---

class CodeParser:
    def __init__(self):
        # Initialize Vertex AI
        project_id = os.environ.get('GCP_PROJECT_ID')
        # Location must be set for Vertex AI to initialize correctly
        location = os.environ.get('GCP_REGION', 'us-central1')
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel('gemini-1.5-flash')

        # Language detection patterns - expanded with more languages
        self.language_patterns = {
            'cobol': [r'\.cob$', r'\.cbl$', r'\.cpy$', r'IDENTIFICATION\s+DIVISION', r'PROGRAM-ID'],
            'c': [r'\.c$', r'\.h$', r'#include\s*<', r'int\s+main\s*\('],
            'cpp': [r'\.cpp$', r'\.cc$', r'\.cxx$', r'\.hpp$', r'#include\s*<iostream>', r'using\s+namespace'],
            'python': [r'\.py$', r'import\s+', r'def\s+', r'class\s+'],
            'java': [r'\.java$', r'public\s+class', r'import\s+java\.'],
            'javascript': [r'\.js$', r'const\s+', r'let\s+', r'function\s+', r'export\s+'],
            'typescript': [r'\.ts$', r'\.tsx$', r'interface\s+', r'type\s+', r'export\s+'],
            'csharp': [r'\.cs$', r'namespace\s+', r'using\s+System', r'public\s+class'],
            'go': [r'\.go$', r'package\s+', r'import\s+\(', r'func\s+'],
            'ruby': [r'\.rb$', r'require\s+', r'def\s+', r'class\s+'],
            'php': [r'\.php$', r'\<\?php', r'function\s+', r'class\s+'],
            'jcl': [r'\.jcl$', r'//\w+\s+JOB', r'//\w+\s+EXEC']
        }

    def detect_language(self, file_path: str, content: str) -> str:
        """Detect programming language from file path and content."""
        for language, patterns in self.language_patterns.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, file_path, re.IGNORECASE):
                    score += 2
                if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                    score += 1
            if score >= 2:
                return language
        return 'unknown'

    def parse_content(self, file_path: str, content: str) -> Tuple[List[CodeEntity], List[CodeRelationship]]:
        """Parse the content of a single file."""
        language = self.detect_language(file_path, content)
        logger.info(f"Detected language for {file_path}: {language}")
        
        ai_entities, ai_relationships = self.extract_with_ai(content, language, file_path)
        
        if not ai_entities:
            logger.info(f"AI returned no entities for {file_path}, falling back to regex.")
            regex_entities, regex_relationships = self.extract_with_regex(content, language, file_path)
            return regex_entities, regex_relationships
        
        return ai_entities, ai_relationships

    def extract_with_ai(self, content: str, language: str, file_path: str) -> Tuple[List[CodeEntity], List[CodeRelationship]]:
        """Extract entities and relationships using Vertex AI."""
        try:
            # Enhanced prompt with more specific instructions and property extraction
            prompt = f"""
            Analyze this {language} code and extract detailed information in a structured format.

            ANALYSIS TASKS:
            1. Functions/methods: Identify name, parameters, return types, visibility, complexity, and purpose
            2. Classes/interfaces: Identify name, fields, methods, parent classes/interfaces, and purpose
            3. Variables/constants: Identify name, data type, scope, initialization value, and purpose
            4. Control flow: Identify loops, conditionals, error handling, and their relationships
            5. Dependencies: Identify external imports, includes, or library usage
            6. Architectural patterns: Identify design patterns or architectural styles if present
            7. Relationships: Identify calls, inheritance, usage, containment between components

            ENTITY TYPES TO IDENTIFY (assign each entity to exactly one of these types):
            * Function: Named procedures or subroutines in code
            * Variable: Local, global, struct/class member variables
            * Struct/Record/Type: User-defined types or records
            * Module/File: Source code files or logical modules
            * Class/Object: Object-oriented components
            * DatabaseTable/Entity: DB tables or files representing structured data
            * ExternalAPI/Service: External endpoints or services the code interacts with
            * BusinessRule/Requirement: Inferred high-level logical conditions
            * Loop/Branch: Control flow structures
            * InputOperation/OutputOperation: File reads/writes, console input, etc.
            * UserInput: Points where user input is captured
            * Job/Script/Program: Main unit of execution

            RELATIONSHIP TYPES TO IDENTIFY:
            * calls: Function → Function — A calls B
            * defines: Module → Function/Variable/Type — Defined in
            * declares: Function → Variable — Declares var
            * uses: Function → Variable — Uses in logic
            * assigns: Function → Variable — Assigns value
            * depends_on: Module/Function → Module/Function — Imports/calls
            * reads_from: Function → Input Source/Table — File/db read
            * writes_to: Function → Output Target/Table — File/db write
            * interacts_with: Function → API/Service — HTTP call, socket, etc.
            * returns: Function → Type/Value — Return type/value
            * composes: Type → Variable — Type composition
            * contains: Type → Field/StructMember — Has-a relationship
            * executes: Job/Script → Module/Function — Entry point
            * calls_with_input_from: Function → User Input — Traced input
            * satisfies: Function/Module → Requirement — Implements business rule
            * triggered_by: Function → Event/Input — Reactive code
            * controls_flow_to: Loop/Branch → Function/Block — Conditional logic
            * spawns: Function → Thread/Process — Concurrency
            * includes: File/Module → File/Module — Header or INCLUDE
            * imports: Module → Module/Package — Import or dependency
            * extends/inherits: Class → Class — Inheritance (OOP)
            * logs_to: Function → Logging Mechanism — Output for monitoring
            * allocates: Function → Memory — Memory allocation operations
            * deallocates: Function → Memory — Memory deallocation operations

            CODE TO ANALYZE:
            ```
            {content[:8000]}
            ```

            REQUIRED OUTPUT FORMAT:
            Return a properly formatted JSON object with these exact keys:
            {{
                "entities": [
                    {{
                        "name": "entity_name", 
                        "entity_type": "function|variable|struct|module|class|...", 
                        "description": "Detailed purpose of this component",
                        "properties": {{
                            "params": ["param1:type1", "param2:type2"],  // For functions/methods
                            "return_type": "return_type",                // For functions/methods
                            "visibility": "public|private|protected",    // For functions/classes/fields
                            "data_type": "type",                        // For variables/constants
                            "parent_class": "name",                     // For classes (inheritance)
                            "interfaces": ["name1", "name2"],           // For classes (implementation)
                            "fields": ["field1:type1", "field2:type2"], // For classes/structs
                            "initializer": "value",                     // For variables/constants
                            "complexity": "low|medium|high",            // For functions (optional)
                            "line_number": 42,                          // Starting line if identifiable
                            "code_length": 10                           // Length in lines if identifiable
                        }}
                    }}
                ],
                "relationships": [
                    {{
                        "source": "source_entity_name", 
                        "target": "target_entity_name", 
                        "relationship_type": "calls|defines|declares|uses|assigns|...", 
                        "context": "Detailed description of this relationship"
                    }}
                ]
            }}
            
            Be precise and thorough. Include all significant code elements. Ensure JSON is correctly formatted.
            IMPORTANT: Every entity must have a name, entity_type, and description field. The properties field should contain additional details specific to the entity type.
            """
            
            response = self.model.generate_content(prompt)
            response_text = response.text
            
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                parsed_data = json.loads(json_text)
                
                entities = []
                for entity_data in parsed_data.get('entities', []):
                    # Extract all fields including any additional properties
                    properties = entity_data.get('properties', {})
                    
                    # If properties are missing, try to extract them from top-level keys
                    for key, value in entity_data.items():
                        if key not in ['name', 'entity_type', 'description', 'properties'] and value is not None:
                            properties[key] = value
                            
                    entities.append(CodeEntity(
                        name=entity_data.get('name'),
                        entity_type=entity_data.get('entity_type'),
                        file_path=file_path,
                        description=entity_data.get('description', ''),
                        properties=properties
                    ))

                relationships = []
                for rel_data in parsed_data.get('relationships', []):
                    relationships.append(CodeRelationship(
                        source=rel_data.get('source'),
                        target=rel_data.get('target'),
                        relationship_type=rel_data.get('relationship_type'),
                        context=rel_data.get('context', '')
                    ))
                
                return entities, relationships
        except Exception as e:
            logger.error(f"AI extraction failed for {file_path}: {e}")
            logger.error(f"Error details: {type(e).__name__}: {str(e)}")
        return [], []

    def extract_with_regex(self, content: str, language: str, file_path: str) -> Tuple[List[CodeEntity], List[CodeRelationship]]:
        """Enhanced fallback regex-based extraction with more patterns and relationship detection."""
        entities = []
        relationships = []
        
        # Enhanced patterns dictionary with more languages and entity types
        patterns = {
            'cobol': {
                'paragraph': r'^[ ]*([A-Z0-9][A-Z0-9-]*)\s*\.',
                'variable': r'^\s*\d+\s+([A-Z0-9-]+)(?:\s+PIC|\s+PICTURE)',
                'file': r'SELECT\s+([A-Z0-9-]+)\s+ASSIGN\s+TO',
                'program': r'PROGRAM-ID.\s+([A-Z0-9-]+)',
                'business_rule': r'^\s*IF\s+(.+?)\s+THEN'
            },
            'python': {
                'function': r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
                'class': r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\(|:)',
                'import': r'import\s+([a-zA-Z_][a-zA-Z0-9_.]*)',
                'from_import': r'from\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import',
                'variable': r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*[^\(]',
                'input_operation': r'input\s*\(',
                'output_operation': r'print\s*\(',
                'loop': r'(?:for|while)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'branch': r'if\s+([^:]+):',
                'with_resource': r'with\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s+([a-zA-Z_][a-zA-Z0-9_]*):',
                'try_except': r'try\s*:'
            },
            'java': {
                'method': r'(?:public|protected|private|static|\s)*\s*[\w\<\>\[\]]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
                'class': r'(?:public|protected|private|static|\s)*\s*(?:class|interface|enum)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'field': r'(?:public|protected|private|static|final|\s)*\s*(?:[\w\<\>\[\]]+)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|;)',
                'import': r'import\s+([a-zA-Z_][a-zA-Z0-9_.]*);',
                'interface': r'interface\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'extends': r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+extends\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'implements': r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+implements\s+([a-zA-Z_][a-zA-Z0-9_,\s]*)',
                'annotation': r'@([a-zA-Z_][a-zA-Z0-9_]*)',
                'try_catch': r'try\s*\{'
            },
            'javascript': {
                'function': r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'arrow_function': r'const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\([^)]*\)\s*=>',
                'class': r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'variable': r'(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=',
                'import': r'import\s+(?:{[^}]*}|[^;]+)\s+from\s+[\'"]([^\'"]+)[\'"]',
                'export': r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'method': r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*{',
                'promise': r'new\s+Promise\s*\(',
                'async_function': r'async\s+function\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'try_catch': r'try\s*{',
                'fetch': r'fetch\s*\('
            },
            'c': {
                'function': r'(?:static|extern|\s)*\s*[\w\*\s]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^\;]*\)\s*\{',
                'struct': r'struct\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\{',
                'define': r'#define\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'include': r'#include\s+[<"]([^>"]+)[>"]',
                'system_include': r'#include\s+<([^>]+)>',
                'project_include': r'#include\s+"([^"]+)"',
                'variable': r'(?:[\w\*\s]+)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|;)',
                'malloc': r'malloc\s*\(',
                'free': r'free\s*\(',
                'typedef': r'typedef\s+struct\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'enum': r'enum\s+([a-zA-Z_][a-zA-Z0-9_]*)'
            },
            'sql': {
                'table': r'CREATE\s+TABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'view': r'CREATE\s+VIEW\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'procedure': r'CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'function': r'CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'trigger': r'CREATE\s+TRIGGER\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'index': r'CREATE\s+INDEX\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'column': r'ALTER\s+TABLE\s+[a-zA-Z_][a-zA-Z0-9_]*\s+ADD\s+COLUMN\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                'foreign_key': r'FOREIGN\s+KEY\s+(?:\([^)]+\))?\s+REFERENCES\s+([a-zA-Z_][a-zA-Z0-9_]*)'
            }
        }
        
        # Default patterns for unknown languages
        default_patterns = {
            'function': r'\b(?:function|func|def|procedure|void|int|string|bool)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
            'class': r'\b(?:class|struct|interface)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            'variable': r'\b(?:var|let|const|int|string|bool|float|double)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            'import': r'\b(?:import|include|require|using)\s+([a-zA-Z_][a-zA-Z0-9_\.\*]+)',
            'file_operation': r'\b(?:open|fopen|read|write|readFile|writeFile|fs\.read|fs\.write)\s*\('
        }
        
        # Use language-specific patterns or default to basic patterns
        lang_patterns = patterns.get(language, default_patterns)
        
        # Special entity for the file itself
        file_entity = CodeEntity(
            name=os.path.basename(file_path),
            entity_type='module',
            file_path=file_path,
            description=f"Source file {file_path}",
            properties={
                "path": file_path,
                "language": language,
                "line_count": content.count('\n') + 1
            }
        )
        entities.append(file_entity)
        
        # Handle C/C++ specific header detection
        if language in ('c', 'cpp') and file_path.endswith(('.h', '.hpp', '.hxx')):
            file_entity.entity_type = 'header_file'
            file_entity.description = f"Header file {file_path}"
            
        # Extract entities based on patterns
        for entity_type, pattern in lang_patterns.items():
            for match in re.finditer(pattern, content, re.MULTILINE if language == 'cobol' else re.IGNORECASE | re.MULTILINE):
                try:
                    name = match.group(1)
                except IndexError:
                    # Some patterns might not have capture groups
                    continue
                
                # Get the code snippet around this entity for better context
                line_start = content[:match.start()].count('\n') + 1
                line_end = line_start + content[match.start():match.end()].count('\n') + 1
                
                # Skip if name is too short or starts with underscore (often internal/private)
                if len(name) <= 1 and not name.isalnum():
                    continue
                
                # Special handling for includes in C/C++
                if entity_type in ('include', 'system_include', 'project_include'):
                    # Create different entity types based on include type
                    if entity_type == 'system_include' or (entity_type == 'include' and match.group(0).strip().startswith('#include <')):
                        include_entity = CodeEntity(
                            name=name,
                            entity_type='system_header',
                            file_path=file_path,
                            description=f"System header {name}",
                            properties={
                                "line_number": line_start,
                                "include_type": "system",
                                "include_syntax": match.group(0).strip()
                            }
                        )
                        entities.append(include_entity)
                        
                        # Add include relationship between file and system header
                        relationships.append(CodeRelationship(
                            source=file_entity.name,
                            target=name,
                            relationship_type='includes',
                            context=f"{file_path} includes system header {name}"
                        ))
                    elif entity_type == 'project_include' or (entity_type == 'include' and match.group(0).strip().startswith('#include "')):
                        include_entity = CodeEntity(
                            name=name,
                            entity_type='project_header',
                            file_path=file_path,
                            description=f"Project header {name}",
                            properties={
                                "line_number": line_start,
                                "include_type": "project",
                                "include_syntax": match.group(0).strip()
                            }
                        )
                        entities.append(include_entity)
                        
                        # Add include relationship between file and project header
                        relationships.append(CodeRelationship(
                            source=file_entity.name,
                            target=name,
                            relationship_type='includes',
                            context=f"{file_path} includes project header {name}"
                        ))
                    continue
                    
                # Get surrounding code for description
                start_pos = max(0, match.start() - 100)
                end_pos = min(len(content), match.end() + 100)
                context_code = content[start_pos:end_pos]
                
                # Add entity with enhanced metadata
                entity = CodeEntity(
                    name=name,
                    entity_type=entity_type,
                    file_path=file_path,
                    description=f"{entity_type.capitalize()} '{name}' in {os.path.basename(file_path)}",
                    properties={
                        "line_number": line_start,
                        "code_length": line_end - line_start,
                        "context_sample": context_code[:200] if len(context_code) > 200 else context_code
                    }
                )
                entities.append(entity)
                
                # Add relationship to file
                relationships.append(CodeRelationship(
                    source=file_entity.name,
                    target=name,
                    relationship_type='defines',
                    context=f"File {os.path.basename(file_path)} defines {entity_type} {name}"
                ))
                
                # For Python imports, add specific relationship
                if language == 'python' and entity_type in ('import', 'from_import'):
                    relationships.append(CodeRelationship(
                        source=file_entity.name,
                        target=name,
                        relationship_type='imports',
                        context=f"Python module {file_entity.name} imports {name}"
                    ))
        
        # Enhanced relationship detection - more sophisticated
        if len(entities) > 1:
            # Process each entity to find potential relationships
            for i, entity in enumerate(entities):
                if entity.entity_type in ('function', 'method', 'paragraph'):
                    # Find potential function calls
                    for j, other_entity in enumerate(entities):
                        if i != j and other_entity.entity_type in ('function', 'method', 'paragraph'):
                            # Check if this function's name appears in the content
                            # Add word boundary to prevent partial matches
                            pattern = r'\b' + re.escape(other_entity.name) + r'\s*\('
                            if re.search(pattern, content, re.MULTILINE):
                                relationships.append(CodeRelationship(
                                    source=entity.name,
                                    target=other_entity.name,
                                    relationship_type='calls',
                                    context=f"Function {entity.name} calls {other_entity.name}"
                                ))
                    
                    # Detect variable usage within functions
                    for j, other_entity in enumerate(entities):
                        if i != j and other_entity.entity_type in ('variable', 'constant'):
                            # Find start and end of function body
                            function_pattern = r'(?:function|def|void|int|string|bool)\s+' + re.escape(entity.name) + r'\s*\([^{]*\)\s*\{(.*?)\}'
                            function_match = re.search(function_pattern, content, re.DOTALL | re.MULTILINE)
                            
                            if function_match:
                                function_body = function_match.group(1)
                                # Check if variable is used in function body
                                var_pattern = r'\b' + re.escape(other_entity.name) + r'\b'
                                if re.search(var_pattern, function_body, re.MULTILINE):
                                    relationships.append(CodeRelationship(
                                        source=entity.name,
                                        target=other_entity.name,
                                        relationship_type='uses',
                                        context=f"Function {entity.name} uses variable {other_entity.name}"
                                    ))
                
                # Check for class inheritance
                if entity.entity_type == 'class':
                    # Different patterns for different languages
                    inheritance_patterns = {
                        'python': r'class\s+' + re.escape(entity.name) + r'\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)',
                        'java': r'class\s+' + re.escape(entity.name) + r'\s+extends\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                        'javascript': r'class\s+' + re.escape(entity.name) + r'\s+extends\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                        'php': r'class\s+' + re.escape(entity.name) + r'\s+extends\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                        'cpp': r'class\s+' + re.escape(entity.name) + r'\s*:\s*(?:public|protected|private)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
                    }
                    
                    pattern = inheritance_patterns.get(language)
                    if pattern:
                        inherit_match = re.search(pattern, content, re.MULTILINE)
                        if inherit_match:
                            parent_class = inherit_match.group(1)
                            # See if we have this parent class in our entities
                            parent_entity = next((e for e in entities if e.name == parent_class), None)
                            if parent_entity:
                                relationships.append(CodeRelationship(
                                    source=entity.name,
                                    target=parent_entity.name,
                                    relationship_type='inherits',
                                    context=f"Class {entity.name} inherits from {parent_entity.name}"
                                ))
                
                # Check for import/include relationships
                if entity.entity_type == 'import':
                    # Add a relationship from the file to the imported module
                    relationships.append(CodeRelationship(
                        source=file_entity.name,
                        target=entity.name,
                        relationship_type='imports',
                        context=f"File {os.path.basename(file_path)} imports {entity.name}"
                    ))
                
                # Detect file operations for reads_from/writes_to relationships
                if entity.entity_type in ('function', 'method') and language == 'python':
                    # Look for open() with 'r' mode - reading
                    read_pattern = r'open\s*\([^,]*,\s*["\']r["\']'
                    if re.search(read_pattern, content, re.MULTILINE):
                        relationships.append(CodeRelationship(
                            source=entity.name,
                            target='file_system',  # Generic target
                            relationship_type='reads_from',
                            context=f"Function {entity.name} reads from files"
                        ))
                    
                    # Look for open() with 'w' or 'a' mode - writing
                    write_pattern = r'open\s*\([^,]*,\s*["\'][wa]["\']'
                    if re.search(write_pattern, content, re.MULTILINE):
                        relationships.append(CodeRelationship(
                            source=entity.name,
                            target='file_system',  # Generic target
                            relationship_type='writes_to',
                            context=f"Function {entity.name} writes to files"
                        ))
                
                # Detect database operations
                if language in ('python', 'java', 'javascript', 'php'):
                    # Look for SQL operations
                    sql_patterns = {
                        'select': r'(?:SELECT|select)\s+.*?\s+(?:FROM|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                        'insert': r'(?:INSERT|insert)\s+(?:INTO|into)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                        'update': r'(?:UPDATE|update)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                        'delete': r'(?:DELETE|delete)\s+(?:FROM|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
                    }
                    
                    if entity.entity_type in ('function', 'method'):
                        # Find function body
                        function_start = content.find(entity.name)
                        if function_start >= 0:
                            function_text = content[function_start:function_start+1000]  # Look at a reasonable chunk
                            
                            # Check for SQL operations
                            for op_type, pattern in sql_patterns.items():
                                for match in re.finditer(pattern, function_text, re.MULTILINE):
                                    table_name = match.group(1)
                                    # Create table entity if it doesn't exist
                                    table_entity = next((e for e in entities if e.name == table_name and e.entity_type == 'database_table'), None)
                                    if not table_entity:
                                        table_entity = CodeEntity(
                                            name=table_name,
                                            entity_type='database_table',
                                            file_path=file_path,
                                            description=f"Database table {table_name} referenced in {file_path}",
                                            properties={"referenced_in": [entity.name]}
                                        )
                                        entities.append(table_entity)
                                    
                                    # Add appropriate relationship
                                    if op_type in ('select'):
                                        relationships.append(CodeRelationship(
                                            source=entity.name,
                                            target=table_name,
                                            relationship_type='reads_from',
                                            context=f"Function {entity.name} reads from table {table_name}"
                                        ))
                                    else:  # insert, update, delete
                                        relationships.append(CodeRelationship(
                                            source=entity.name,
                                            target=table_name,
                                            relationship_type='writes_to',
                                            context=f"Function {entity.name} writes to table {table_name}"
                                        ))
        
        return entities, relationships

# --- Cloud Function Entry Point ---

# Initialize clients and parser globally to be reused across warm invocations
storage_client = storage.Client()
parser = CodeParser()
PARSED_DATA_BUCKET = os.environ.get('PARSED_DATA_BUCKET')

@functions_framework.cloud_event
def code_parser_entrypoint(cloud_event):
    """GCS-triggered Cloud Function to parse a single code file."""
    data = cloud_event.data
    bucket_name = data["bucket"]
    file_name = data["name"]

    logger.info(f"Processing {file_name} from {bucket_name}.")

    try:
        # Download file content
        source_bucket = storage_client.bucket(bucket_name)
        blob = source_bucket.blob(file_name)
        if not blob.exists():
            logger.error(f"File {file_name} does not exist.")
            return

        raw_content = blob.download_as_bytes()
        content = ""
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                content = raw_content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            content = raw_content.decode('utf-8', errors='replace')

        # Parse the code
        entities, relationships = parser.parse_content(file_name, content)
        
        # Prepare data for upload
        repo_id = file_name.split('/')[1] if file_name.startswith('cloned_repos/') else 'unknown_repo'
        output_data = {
            "repo_id": repo_id,
            "filename": file_name,
            "entities": [e.to_dict() for e in entities],
            "relationships": [r.to_dict() for r in relationships]
        }
        
        # Upload results to the parsed data bucket
        if not PARSED_DATA_BUCKET:
            raise ValueError("PARSED_DATA_BUCKET environment variable not set.")
        
        destination_bucket = storage_client.bucket(PARSED_DATA_BUCKET)
        # Create a unique name for the JSON output file
        destination_blob_name = f'parsed_data/{repo_id}/{os.path.basename(file_name)}.json'
        destination_blob = destination_bucket.blob(destination_blob_name)
        
        destination_blob.upload_from_string(
            json.dumps(output_data, indent=2),
            content_type='application/json'
        )
        
        logger.info(f"Successfully parsed {file_name} and uploaded results to {destination_blob_name}.")

    except Exception as e:
        logger.error(f"Failed to process {file_name}: {e}", exc_info=True)
        raise