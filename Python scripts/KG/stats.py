# get_stats.py

from SPARQLWrapper import SPARQLWrapper, JSON

# --- 1. CONFIGURATION ---
# The only thing you might need to change is the endpoint URL
SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
USER_AGENT = "KG-Statistics-Counter/1.0"

# --- 2. NAMESPACES AND QUERIES ---
# Define all necessary prefixes
NAMESPACES = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
"""

# Define the specific COUNT queries
ENTITY_COUNT_QUERY = """
    SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE {
        ?s a ?type .
        FILTER(STRSTARTS(STR(?s), "http://cgi.di.uoa.gr/witcher/resource/"))
    }
"""

CLASS_COUNT_QUERY = """
    SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE {
        ?s a owl:Class .
        FILTER(STRSTARTS(STR(?s), "http://cgi.di.uoa.gr/witcher/ontology#"))
    }
"""

PROPERTY_COUNT_QUERY = """
    SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE {
        ?s a rdf:Property .
        FILTER(STRSTARTS(STR(?s), "http://cgi.di.uoa.gr/witcher/ontology#"))
    }
"""

# --- 3. HELPER FUNCTION ---
def get_count(sparql_query: str) -> int:
    """Executes a SPARQL COUNT query and returns the integer result."""
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    full_query = NAMESPACES + sparql_query
    sparql.setQuery(full_query)
    sparql.setReturnFormat(JSON)
    sparql.agent = USER_AGENT
    
    try:
        results = sparql.query().convert()["results"]["bindings"]
        if results:
            # The count value is in the first result, under the 'count' variable
            return int(results[0]['count']['value'])
    except Exception as e:
        print(f"  - Query failed: {e}")
    
    return 0

# --- 4. MAIN EXECUTION ---
def main():
    """Runs all count queries and prints the results."""
    print(f"Querying SPARQL endpoint at: {SPARQL_ENDPOINT_URL}\n")
    
    print("Calculating total number of Entities...")
    entity_count = get_count(ENTITY_COUNT_QUERY)
    
    print("Calculating total number of Classes...")
    class_count = get_count(CLASS_COUNT_QUERY)
    
    print("Calculating total number of Properties...")
    property_count = get_count(PROPERTY_COUNT_QUERY)
    
    print("\n" + "="*30)
    print("--- Knowledge Graph Statistics ---")
    print(f"  - Total Entities:   {entity_count}")
    print(f"  - Total Classes:    {class_count}")
    print(f"  - Total Properties: {property_count}")
    print("="*30)

if __name__ == "__main__":
    main()