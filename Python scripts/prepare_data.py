# prepare_data_enriched.py
import json
from SPARQLWrapper import SPARQLWrapper, JSON
from llama_index.core import Document
from collections import defaultdict
from tqdm import tqdm

# --- 1. CONFIGURATION ---
SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
USER_AGENT = "RAG-Data-Prep/1.0"

# --- 2. THE DEFINITIVE NAMESPACES STRING ---
namespaces = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
"""

# --- 3. HELPER FUNCTIONS ---
def execute_sparql_query(query):
    """Executes a SPARQL query and returns the results."""
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(namespaces + query)
    sparql.setReturnFormat(JSON)
    sparql.agent = USER_AGENT
    try:
        return sparql.query().convert()["results"]["bindings"]
    except Exception as e:
        print(f"\nSPARQL query failed. Error: {e}")
        return None

def get_name(uri, label_cache):
    """Gets the rdfs:label for a URI, or cleans the URI as a fallback."""
    if uri in label_cache:
        return label_cache[uri]
    if uri:
        return uri.split('/')[-1].replace('_', ' ')
    return ""

def extract_and_format_enriched_data():
    """
    Queries GraphDB to get a rich, "de-siloed" description for each entity
    and formats the data for LlamaIndex.
    """
    
    # Step 1: Build a label cache for efficiency
    print("Building label cache...")
    label_cache_query = "SELECT ?s ?label WHERE { ?s rdfs:label ?label . }"
    label_results = execute_sparql_query(label_cache_query)
    label_cache = {res['s']['value']: res['label']['value'] for res in label_results} if label_results else {}
    
    # --- Step 2: Extract Enriched ENTITY Data with Knowledge Duplication ---
    print("Extracting enriched entity data...")
    entity_docs = []
    
    print("  - Step 2a: Fetching all entity URIs...")
    entity_uri_query = "SELECT DISTINCT ?s WHERE { ?s a ?type . FILTER(STRSTARTS(STR(?s), STR(dbr:))) }"
    entity_uri_results = execute_sparql_query(entity_uri_query)
    if not entity_uri_results:
        print("Error: Could not fetch any entity URIs. Please check the initial query.")
        return [], [], []
    
    entity_uris = [res['s']['value'] for res in entity_uri_results]
    print(f"  - Found {len(entity_uris)} total entity URIs.")

    print("  - Step 2b: Hydrating each entity with de-siloed properties...")
    for uri in tqdm(entity_uris, desc="Hydrating Entities"):
        # This powerful query fetches the entity's own details, its types, and its properties.
        hydration_query = f"""
        SELECT ?label (GROUP_CONCAT(DISTINCT ?aka; SEPARATOR=", ") AS ?aliases) 
                       (GROUP_CONCAT(DISTINCT ?typeLabel; SEPARATOR=", ") AS ?types)
                       (GROUP_CONCAT(DISTINCT ?prop_info; SEPARATOR=" | ") AS ?properties)
        WHERE {{
            BIND(<{uri}> AS ?s)
            
            OPTIONAL {{ ?s rdfs:label ?label . }}
            OPTIONAL {{ ?s witcher:aka ?aka . }}
            
            # Get all properties and their values' labels to create descriptive text
            OPTIONAL {{
                ?s ?prop_uri ?value_uri .
                ?prop_uri rdfs:label ?prop_label .
                OPTIONAL {{ ?value_uri rdfs:label ?value_label . }}
                # Create a single string like "Profession: Armorer"
                BIND(CONCAT(STR(?prop_label), ": ", COALESCE(?value_label, "")) AS ?prop_info)
                FILTER(STRSTARTS(STR(?prop_uri), STR(witcher:)))
            }}
            
            # This part is required to get the types
            ?s a ?type_uri .
            OPTIONAL {{ ?type_uri rdfs:label ?typeLabel . }}
        }}
        GROUP BY ?label
        LIMIT 1
        """
        
        entity_details = execute_sparql_query(hydration_query)
        if not entity_details:
            continue
        
        res = entity_details[0]
        name = get_name(uri, label_cache)
        
        # --- Document Construction ---
        text_lines = [f"This document is about the entity named {name}."]
        
        if res.get('aliases') and res['aliases']['value']:
            text_lines.append(f"It is also known as: {res['aliases']['value']}.")
        
        if res.get('types') and res['types']['value']:
            # Make the relationship explicit for the embedding model
            text_lines.append(f"It is a type of: {res['types']['value']}.")
        
        if res.get('properties') and res['properties']['value']:
            # Add all the "Property: Value" pairs
            prop_list = [p.strip() for p in res['properties']['value'].split('|')]
            text_lines.append("Its known properties and relationships include:")
            for prop_str in prop_list:
                # Add a simple check to avoid empty property strings
                if ":" in prop_str and not prop_str.endswith(":"):
                    text_lines.append(f"- {prop_str}")
        
        text_content = "\n".join(text_lines)
        entity_docs.append(Document(
            text=text_content, 
            metadata={"uri": uri, "name": name, "type": "Entity"}
        ))

    # --- Step 3: Extract CLASS Data ---
    print("Extracting class data...")
    class_docs = []
    class_query = "SELECT ?s ?subClassOf WHERE {{ ?s a owl:Class . OPTIONAL {{ ?s rdfs:subClassOf ?subClassOf . }} FILTER(STRSTARTS(STR(?s), STR(witcher:))) }}"
    class_results = execute_sparql_query(class_query)
    if class_results:
        for res in class_results:
            name = get_name(res['s']['value'], label_cache)
            parent = get_name(res.get('subClassOf', {}).get('value'), label_cache) if res.get('subClassOf') else "Thing"
            text_content = f"Class: {name}.\nParent Class: {parent}."
            class_docs.append(Document(text=text_content, metadata={"uri": res['s']['value'], "name": name, "type": "Class"}))

    # --- Step 4: Extract PROPERTY Data ---
    print("Extracting property data...")
    prop_docs = []
    prop_query = f"SELECT DISTINCT ?p WHERE {{ ?s ?p ?o }}"
    prop_results = execute_sparql_query(prop_query)
    if prop_results:
        for res in prop_results:
            name = get_name(res['p']['value'], label_cache)
            text_content = f"Property: {name}."
            prop_docs.append(Document(text=text_content, metadata={"uri": res['p']['value'], "name": name, "type": "Property"}))

    print(f"Successfully extracted and hydrated {len(entity_docs)} entities, {len(class_docs)} classes, and {len(prop_docs)} properties.")
    return entity_docs, class_docs, prop_docs

if __name__ == "__main__":
    extract_and_format_enriched_data()
    print("Enriched data preparation complete.")


# import json
# from SPARQLWrapper import SPARQLWrapper, JSON
# from llama_index.core import Document
# from collections import defaultdict
# from tqdm import tqdm

# SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
# USER_AGENT = "WitcherKG-Benchmark-Generator/1.0"
# namespaces = """
#     PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
#     PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
#     PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
#     PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
# """

# def execute_sparql_query(query):
#     sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
#     sparql.setQuery(query)
#     sparql.setReturnFormat(JSON)
#     sparql.agent = "RAG-Data-Prep/1.0"
#     try:
#         return sparql.query().convert()["results"]["bindings"]
#     except Exception as e:
#         print(f"\nSPARQL query failed. Error: {e}")
#         return None

# def get_name(uri, label_cache):
#     if uri in label_cache:
#         return label_cache[uri]
#     return uri.split('/')[-1].replace('_', ' ')
    

# def get_name(uri: str, label_cache: dict) -> str:
#     """Gets the rdfs:label for a URI, or cleans the URI as a fallback."""
#     if not uri: return ""
#     # Prefer the official label if it exists
#     if uri in label_cache:
#         return label_cache[uri]
#     # Fallback for anything without a label
#     return uri.split('#')[-1].split('/')[-1].replace('_', ' ')

# def extract_and_format_enriched_data():
#     """
#     Queries GraphDB to get a rich, contextual description for each entity
#     using a robust two-step hydration process.
#     """

#     # 1. Build a label cache for efficiency
#     print("Building label cache...")
#     label_cache_query = f"{namespaces} SELECT ?s ?label WHERE {{ ?s rdfs:label ?label . }}"
#     label_results = execute_sparql_query(label_cache_query)
#     label_cache = {res['s']['value']: res['label']['value'] for res in label_results}

#     # --- 2. Extract Enriched ENTITY Data ---
#     print("Extracting enriched entity data...")
#     entity_docs = []

#     # --- STEP 1: Get all entity URIs using your simple, proven query ---
#     print("Step 1: Fetching all entity URIs...")
#     entity_uri_query = f"""{namespaces} SELECT DISTINCT ?s WHERE {{ ?s a ?type . FILTER(STRSTARTS(STR(?s), STR(dbr:))) }}"""
#     entity_uri_results = execute_sparql_query(entity_uri_query)
#     if not entity_uri_results:
#         print("Error: Could not fetch any entity URIs. Please check the initial query.")
#         return [], [], []
    
#     entity_uris = [res['s']['value'] for res in entity_uri_results]
#     print(f"Found {len(entity_uris)} total entity URIs.")

#     # --- STEP 2: "Hydrate" each entity with its details ---
#     print("Step 2: Hydrating each entity with its properties...")
#     for uri in tqdm(entity_uris, desc="Hydrating Entities"):
#         # This query is targeted to a single entity and is very robust.
#         hydration_query = f"""{namespaces}
#         SELECT ?label (GROUP_CONCAT(DISTINCT ?aka; SEPARATOR=", ") AS ?aliases) 
#                        (GROUP_CONCAT(DISTINCT ?typeLabel; SEPARATOR=", ") AS ?types)
#                        ?raceLabel ?professionLabel
#         WHERE {{
#             BIND(<{uri}> AS ?s)
            
#             OPTIONAL {{ ?s rdfs:label ?label . }}
#             OPTIONAL {{ ?s witcher:aka ?aka . }}
#             OPTIONAL {{ 
#                 ?s witcher:race ?race_uri .
#                 OPTIONAL {{ ?race_uri rdfs:label ?race_label . }}
#             }}
#             OPTIONAL {{ 
#                 ?s witcher:profession ?prof_uri .
#                 OPTIONAL {{ ?prof_uri rdfs:label ?prof_label . }}
#             }}
#             # This part is required to get the types
#             ?s a ?type_uri .
#             OPTIONAL {{ ?type_uri rdfs:label ?typeLabel . }}
#         }}
#         GROUP BY ?label ?raceLabel ?professionLabel
#         LIMIT 1
#         """
        
#         entity_details = execute_sparql_query(hydration_query)
#         if not entity_details:
#             continue
        
#         res = entity_details[0] # We only expect one result
        
#         name = res.get('label', {}).get('value', uri.split('/')[-1].replace('_', ' '))
        
#         # --- Document Construction ---
#         text_lines = [f"Entity: {name}."]
        
#         if res.get('aliases') and res['aliases']['value']:
#             text_lines.append(f"Also Known As: {res['aliases']['value']}.")
        
#         if res.get('types') and res['types']['value']:
#             text_lines.append(f"Types: {res['types']['value']}.")
        
#         if res.get('raceLabel'):
#             text_lines.append(f"Race: {res['raceLabel']['value']}.")

#         if res.get('professionLabel'):
#             text_lines.append(f"Profession: {res['professionLabel']['value']}.")
        
#         text_content = "\n".join(text_lines)
#         entity_docs.append(Document(
#             text=text_content, 
#             metadata={"uri": uri, "name": name, "type": "Entity"}
#         ))

    
#     # 3. Extract CLASSES
#     print("Extracting classes...")
#     class_docs = []
#     class_query = f"{namespaces} SELECT ?s ?subClassOf WHERE {{ ?s a owl:Class . OPTIONAL {{ ?s rdfs:subClassOf ?subClassOf . }} FILTER(STRSTARTS(STR(?s), STR(witcher:))) }}"
#     class_results = execute_sparql_query(class_query)
#     for res in class_results:
#         name = get_name(res['s']['value'], label_cache)
#         parent = get_name(res.get('subClassOf', {}).get('value'), label_cache) if res.get('subClassOf') else "Thing"
#         text_content = f"Class: {name}.\nParent Class: {parent}."
#         class_docs.append(Document(text=text_content, metadata={"uri": res['s']['value'], "name": name, "type": "Class"}))

#     # 4. Extract PROPERTIES
#     print("Extracting properties...")
#     prop_docs = []
#     prop_query = f"{namespaces} SELECT DISTINCT ?p WHERE {{ ?s ?p ?o }}"
#     prop_results = execute_sparql_query(prop_query)
#     for res in prop_results:
#         uri = res['p']['value']
#         name = get_name(uri, label_cache)
#         text_content = f"Property: {name}."
#         prop_docs.append(Document(text=text_content, metadata={"uri": uri, "name": name, "type": "Property"}))

#     print(f"Extracted {len(entity_docs)} entities, {len(class_docs)} classes, {len(prop_docs)} properties.")
#     return entity_docs, class_docs, prop_docs

#     print(f"Successfully extracted and hydrated {len(entity_docs)} entities.")
#     return entity_docs, [], [] # Return empty lists for now for brevity

# if __name__ == "__main__":
#     extract_and_format_enriched_data()
#     print("Enriched data preparation complete.")



# import json
# from SPARQLWrapper import SPARQLWrapper, JSON
# from llama_index.core import Document
# from collections import defaultdict

# SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
# USER_AGENT = "WitcherKG-Benchmark-Generator/1.0"
# namespaces = """
#     PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
#     PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
#     PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
# """

# # --- HELPER FUNCTIONS ---
# def execute_sparql_query(query):
#     # This is the function from your working script.
#     sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
#     sparql.setQuery(query)
#     sparql.setReturnFormat(JSON)
#     sparql.agent = USER_AGENT
#     try:
#         results = sparql.query().convert()
#         return results["results"]["bindings"]
#     except Exception as e:
#         print(f"\nSPARQL query failed. Error: {e}")
#         return None

# def get_name(uri: str, label_cache: dict) -> str:
#     """Gets the rdfs:label for a URI, or cleans the URI as a fallback."""
#     if not uri: return ""
#     # Prefer the official label if it exists
#     if uri in label_cache:
#         return label_cache[uri]
#     # Fallback for anything without a label
#     return uri.split('#')[-1].split('/')[-1].replace('_', ' ')

# def extract_and_format_data():
#     """Queries GraphDB and formats data for LlamaIndex."""
    
#     # 1. Build a label cache for efficiency
#     print("Building label cache...")
#     label_cache_query = f"{namespaces} SELECT ?s ?label WHERE {{ ?s rdfs:label ?label . }}"
#     label_results = execute_sparql_query(label_cache_query)
#     label_cache = {res['s']['value']: res['label']['value'] for res in label_results}
    
#     # 2. Extract ENTITIES
#     print("Extracting entities...")
#     entity_docs = []
#     entity_query = f"{namespaces} SELECT DISTINCT ?s ?type WHERE {{ ?s a ?type . FILTER(STRSTARTS(STR(?s), STR(dbr:))) }}"
#     entity_results = execute_sparql_query(entity_query)
    
#     # Group types by entity
#     entities = defaultdict(list)
#     for res in entity_results:
#         entities[res['s']['value']].append(get_name(res['type']['value'], label_cache))
        
#     for uri, types in entities.items():
#         name = get_name(uri, label_cache)
#         # Create a rich text description for embedding
#         text_content = f"Entity: {name}.\nTypes: {', '.join(types)}."
#         entity_docs.append(Document(text=text_content, metadata={"uri": uri, "name": name, "type": "Entity"}))

#     # 3. Extract CLASSES
#     print("Extracting classes...")
#     class_docs = []
#     class_query = f"{namespaces} SELECT ?s ?subClassOf WHERE {{ ?s a owl:Class . OPTIONAL {{ ?s rdfs:subClassOf ?subClassOf . }} FILTER(STRSTARTS(STR(?s), STR(witcher:))) }}"
#     class_results = execute_sparql_query(class_query)
#     for res in class_results:
#         name = get_name(res['s']['value'], label_cache)
#         parent = get_name(res.get('subClassOf', {}).get('value'), label_cache) if res.get('subClassOf') else "Thing"
#         text_content = f"Class: {name}.\nParent Class: {parent}."
#         class_docs.append(Document(text=text_content, metadata={"uri": res['s']['value'], "name": name, "type": "Class"}))

#     # 4. Extract PROPERTIES
#     print("Extracting properties...")
#     prop_docs = []
#     prop_query = f"{namespaces} SELECT DISTINCT ?p WHERE {{ ?s ?p ?o }}"
#     prop_results = execute_sparql_query(prop_query)
#     for res in prop_results:
#         uri = res['p']['value']
#         name = get_name(uri, label_cache)
#         text_content = f"Property: {name}."
#         prop_docs.append(Document(text=text_content, metadata={"uri": uri, "name": name, "type": "Property"}))

#     print(f"Extracted {len(entity_docs)} entities, {len(class_docs)} classes, {len(prop_docs)} properties.")
#     return entity_docs, class_docs, prop_docs

# if __name__ == "__main__":
#     entities, classes, properties = extract_and_format_data()
#     print("Data preparation complete.")