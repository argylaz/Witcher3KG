# prepare_data.py
import json
from SPARQLWrapper import SPARQLWrapper, JSON
from llama_index.core import Document
from collections import defaultdict

SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
USER_AGENT = "WitcherKG-Benchmark-Generator/1.0"
namespaces = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
"""

# --- HELPER FUNCTIONS ---
def execute_sparql_query(query):
    # This is the function from your working script.
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.agent = USER_AGENT
    try:
        results = sparql.query().convert()
        return results["results"]["bindings"]
    except Exception as e:
        print(f"\nSPARQL query failed. Error: {e}")
        return None

def get_name(uri: str, label_cache: dict) -> str:
    """Gets the rdfs:label for a URI, or cleans the URI as a fallback."""
    if not uri: return ""
    # Prefer the official label if it exists
    if uri in label_cache:
        return label_cache[uri]
    # Fallback for anything without a label
    return uri.split('#')[-1].split('/')[-1].replace('_', ' ')

def extract_and_format_data():
    """Queries GraphDB and formats data for LlamaIndex."""
    
    # 1. Build a label cache for efficiency
    print("Building label cache...")
    label_cache_query = f"{namespaces} SELECT ?s ?label WHERE {{ ?s rdfs:label ?label . }}"
    label_results = execute_sparql_query(label_cache_query)
    label_cache = {res['s']['value']: res['label']['value'] for res in label_results}
    
    # 2. Extract ENTITIES
    print("Extracting entities...")
    entity_docs = []
    entity_query = f"{namespaces} SELECT DISTINCT ?s ?type WHERE {{ ?s a ?type . FILTER(STRSTARTS(STR(?s), STR(dbr:))) }}"
    entity_results = execute_sparql_query(entity_query)
    
    # Group types by entity
    entities = defaultdict(list)
    for res in entity_results:
        entities[res['s']['value']].append(get_name(res['type']['value'], label_cache))
        
    for uri, types in entities.items():
        name = get_name(uri, label_cache)
        # Create a rich text description for embedding
        text_content = f"Entity: {name}.\nTypes: {', '.join(types)}."
        entity_docs.append(Document(text=text_content, metadata={"uri": uri, "name": name, "type": "Entity"}))

    # 3. Extract CLASSES
    print("Extracting classes...")
    class_docs = []
    class_query = f"{namespaces} SELECT ?s ?subClassOf WHERE {{ ?s a owl:Class . OPTIONAL {{ ?s rdfs:subClassOf ?subClassOf . }} FILTER(STRSTARTS(STR(?s), STR(witcher:))) }}"
    class_results = execute_sparql_query(class_query)
    for res in class_results:
        name = get_name(res['s']['value'], label_cache)
        parent = get_name(res.get('subClassOf', {}).get('value'), label_cache) if res.get('subClassOf') else "Thing"
        text_content = f"Class: {name}.\nParent Class: {parent}."
        class_docs.append(Document(text=text_content, metadata={"uri": res['s']['value'], "name": name, "type": "Class"}))

    # 4. Extract PROPERTIES
    print("Extracting properties...")
    prop_docs = []
    prop_query = f"{namespaces} SELECT DISTINCT ?p WHERE {{ ?s ?p ?o }}"
    prop_results = execute_sparql_query(prop_query)
    for res in prop_results:
        uri = res['p']['value']
        name = get_name(uri, label_cache)
        text_content = f"Property: {name}."
        prop_docs.append(Document(text=text_content, metadata={"uri": uri, "name": name, "type": "Property"}))

    print(f"Extracted {len(entity_docs)} entities, {len(class_docs)} classes, {len(prop_docs)} properties.")
    return entity_docs, class_docs, prop_docs

if __name__ == "__main__":
    entities, classes, properties = extract_and_format_data()
    print("Data preparation complete.")