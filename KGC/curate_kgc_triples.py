# curate_kgc_triples.py

import argparse
import random
import os
import time
from SPARQLWrapper import SPARQLWrapper, JSON

# --- 1. CONFIGURATION ---
SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
OUTPUT_FILE = "accepted_triples.tsv"
PROGRESS_FILE = "curation_progress.txt"

# Define the target classes we want to focus on for our benchmark
TARGET_CLASSES = [
    "witcher:The_Witcher_3_characters",
    "witcher:The_Witcher_3_quests",
    "witcher:The_Witcher_3_items"
]

# Define properties to exclude (e.g., ones that aren't factual relationships)
PROPERTIES_TO_EXCLUDE = [
    "rdf:type",
    "rdfs:label",
    "geo:hasGeometry",
    "geo:asWKT",
    "witcher:hasInGameCoordinates",
    "witcher:isPartOf"
]

# --- 2. HELPER FUNCTIONS ---
def execute_sparql_query(query, endpoint, namespaces):
    """Executes a SPARQL query and returns the results."""
    sparql = SPARQLWrapper(endpoint)
    full_query = namespaces + query
    sparql.setQuery(full_query)
    sparql.setReturnFormat(JSON)
    try:
        return sparql.query().convert()["results"]["bindings"]
    except Exception as e:
        print(f"\nSPARQL query failed: {e}")
        return None

def clear_screen():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

# --- 3. MAIN SCRIPT LOGIC ---
def main():
    parser = argparse.ArgumentParser(
        description="Interactively review and curate triples for a KGC benchmark.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--fetch-limit", 
        type=int, 
        default=5000,
        help="The number of random triples to fetch from the KG for review."
    )
    args = parser.parse_args()

    namespaces = """
        PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX geo: <http://www.opengis.net/ont/geosparql#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
    """

    # --- Step 1: Fetch a large, random sample of candidate triples ---
    print("Fetching candidate triples from the Knowledge Graph...")
    
    # Create a VALUES clause for our target classes
    class_values = " ".join([f"{c}" for c in TARGET_CLASSES])
    
    # Create a FILTER clause to exclude unwanted properties
    prop_filters = " && ".join([f"?r != {p}" for p in PROPERTIES_TO_EXCLUDE])
    
    query = f"""
    SELECT ?h ?r ?t ?hLabel ?rLabel ?tLabel
    WHERE {{
        VALUES ?class {{ {class_values} }}
        ?h a ?class .
        ?h ?r ?t .

        # Ensure the relation is part of our ontology
        FILTER(STRSTARTS(STR(?r), STR(witcher:)))
        # Exclude non-factual properties
        FILTER({prop_filters})
        # Ensure the tail is an entity, not a literal value
        FILTER(isIRI(?t))

        # Get labels for readability
        ?h rdfs:label ?hLabel .
        ?t rdfs:label ?tLabel .
        OPTIONAL {{ ?r rdfs:label ?rLabel . }}
    }}
    ORDER BY RAND()
    LIMIT {args.fetch_limit}
    """
    
    all_triples = execute_sparql_query(query, SPARQL_ENDPOINT_URL, namespaces)
    
    if not all_triples:
        print("Could not fetch any triples. Please check your SPARQL endpoint and query.")
        return
        
    print(f"Fetched {len(all_triples)} candidate triples for review.")

    # --- Step 2: Load progress and existing curated triples ---
    start_index = 0
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            try:
                start_index = int(f.read())
                print(f"Resuming from triple #{start_index + 1}.")
            except ValueError:
                pass # File is empty or corrupt, start from 0
    
    # Use 'a' mode to append to the file if it already exists
    output_file_handle = open(OUTPUT_FILE, 'a', encoding='utf-8')

    # --- Step 3: The Interactive Review Loop ---
    quit_flag = False
    accepted_count = 0

    try:
        for i, triple in enumerate(all_triples):
            if i < start_index:
                continue

            clear_screen()
            
            h_uri = triple['h']['value']
            r_uri = triple['r']['value']
            t_uri = triple['t']['value']
            
            h_label = triple['hLabel']['value']
            t_label = triple['tLabel']['value']
            # Use the URI fragment if a property has no label
            r_label = triple.get('rLabel', {}).get('value', r_uri.split('#')[-1])

            print(f"--- Reviewing Triple {i + 1} / {len(all_triples)} ---")
            print(f"    (Accepted so far: {accepted_count})")
            print("-" * 50)
            print(f"  Head:     {h_label}")
            print(f"  Relation: {r_label}")
            print(f"  Tail:     {t_label}")
            print("-" * 50)
            print("Is this a well-formed, factual triple?")

            while True:
                choice = input("Accept (a) / Reject (r) / Quit (q): ").lower().strip()
                if choice == 'a':
                    # Save in head<TAB>relation<TAB>tail format using URIs
                    output_file_handle.write(f"{h_uri}\t{r_uri}\t{t_uri}\n")
                    accepted_count += 1
                    print("  -> Accepted.")
                    time.sleep(0.5)
                    break
                elif choice == 'r':
                    print("  -> Rejected.")
                    time.sleep(0.5)
                    break
                elif choice == 'q':
                    print("  -> Quitting and saving progress.")
                    quit_flag = True
                    break
                else:
                    print("  Invalid input. Please enter 'a', 'r', or 'q'.")
            
            # Save progress after each decision
            with open(PROGRESS_FILE, 'w') as f:
                f.write(str(i + 1))
            
            if quit_flag:
                break
    finally:
        # --- Step 4: Cleanup ---
        output_file_handle.close()
        clear_screen()
        print("--- Curation Session Ended ---")
        print(f"You accepted {accepted_count} new triples in this session.")
        print(f"All accepted triples have been saved to '{OUTPUT_FILE}'.")
        print(f"Your progress has been saved. You can run the script again to resume.")

if __name__ == "__main__":
    main()