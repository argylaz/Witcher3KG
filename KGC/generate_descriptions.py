import os
import time
import re
from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef
import requests
import json
import glob

# --- Configuration ---
OPENROUTER_API_KEY = ""

# The graph is our source of truth for text
KG_FULL_PATH = '../RDF/Witcher3KG_full.ttl' 

# The KGC dataset files define our scope
KGC_DATASET_DIR = './dataset_v3/' # Assumes train.tsv, etc., are in the same directory

# Output files
ENTITY_DESC_PATH = 'entity_desc.tsv'
RELATION_DESC_PATH = 'relation_desc.tsv'

# --- Namespaces ---
witcher = Namespace("http://cgi.di.uoa.gr/witcher/ontology#")
dbr = Namespace("http://cgi.di.uoa.gr/witcher/resource/")

# Model
MODEL_NAME = "qwen/qwen3-4b:free" 

# --- Helper Functions (Unchanged) ---
def prepare_text_for_summarization(full_text: str):
    MAX_CHARS = 150000
    if len(full_text) <= MAX_CHARS: return full_text
    print(f"  - WARNING: Text extremely long ({len(full_text)} chars). Truncating.")
    return (full_text[:75000] + "\n\n--- [CONTENT TRUNCATED] ---\n\n" + full_text[-75000:])

import requests # Make sure this is imported at the top of your file
import json
import time

# ... (keep the rest of your script, including configuration and other helpers) ...
def generate_llm_summary(prompt_text, max_retries=4): # Increased retries to 4
    """
    Sends a prompt to the LLM with robust error handling, a universal delay,
    and aggressive exponential backoff for rate limiting.
    """
    
    # --- The Universal Delay ---
    # ALWAYS wait before making a request. This is the most critical fix.
    time.sleep(2) # Wait 2 seconds between every single attempt.

    for attempt in range(max_retries):
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost/WitcherKG",
                "X-Title": "Witcher3-KG-Project",
            }
            data_payload = {
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt_text}],
                "max_tokens": 1024,
                "stream": False,
            }

            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                data=json.dumps(data_payload),
                timeout=60 # Add a timeout to prevent hanging forever
            )

            # Check for HTTP errors (like 400, 429, 500)
            response.raise_for_status() 

            result = response.json()
            summary = result['choices'][0]['message']['content'].strip()
            
            return summary # Success!
            
        except requests.exceptions.HTTPError as http_err:
            # This is a specific error from the server (e.g., 429, 503)
            print(f"  - HTTP Error (attempt {attempt+1}/{max_retries}): {http_err} - Response: {response.text}")
            # --- Aggressive Exponential Backoff ---
            wait_time = 5 * (2 ** attempt) # Waits 5s, then 10s, then 20s, etc.
            print(f"    Server is busy. Waiting {wait_time} seconds before retrying...")
            time.sleep(wait_time)
            
        except Exception as e:
            # This is a different error (e.g., network connection failed)
            print(f"  - An unexpected error occurred (attempt {attempt+1}/{max_retries}): {e}")
            wait_time = 5 * (2 ** attempt)
            print(f"    Waiting {wait_time} seconds before retrying...")
            time.sleep(wait_time)
            
    # If all retries fail, return None
    return None

# --- NEW Helper to get target URIs ---
def load_kgc_dataset_uris(dataset_dir):
    """Reads all .tsv files in a directory to get a unique set of entities and relations."""
    target_entities = set()
    target_relations = set()
    
    tsv_files = glob.glob(os.path.join(dataset_dir, '*.tsv'))
    print(f"Found KGC dataset files: {tsv_files}")

    for file_path in tsv_files:
        if "desc" in file_path: continue # Don't read our own output files
        print(f"  - Reading targets from {os.path.basename(file_path)}")
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) == 3:
                    h, r, t = parts
                    target_entities.add(h)
                    target_entities.add(t)
                    target_relations.add(r)
                    
    print(f"\nFound {len(target_entities)} unique entities and {len(target_relations)} unique relations in the KGC dataset.")
    return target_entities, target_relations

# --- Main Processing Logic ---
def process_knowledge_graph():
    
    # --- Step 1: Identify all entities and relations we need to process ---
    target_entities, target_relations = load_kgc_dataset_uris(KGC_DATASET_DIR)

    g = Graph()
    print(f"\nLoading full knowledge graph from {KG_FULL_PATH}...")
    g.parse(KG_FULL_PATH, format='turtle')
    print(f"Graph loaded with {len(g)} triples.")

    # --- Step 2: Generate Descriptions for TARGET ENTITIES ---
    print("\n--- Generating descriptions for KGC Entities ---")
    entity_query = """
        SELECT DISTINCT ?entity ?label ?fullText
        WHERE {
            ?entity rdfs:label ?label .
            ?entity witcher:hasFullText ?fullText .
        }
    """
    
    processed_uris = set()
    if os.path.exists(ENTITY_DESC_PATH):
        with open(ENTITY_DESC_PATH, 'r', encoding='utf-8') as f:
            next(f); [processed_uris.add(line.split('\t')[0]) for line in f]
    print(f"Found {len(processed_uris)} entities already processed. Resuming.")

    with open(ENTITY_DESC_PATH, 'a', encoding='utf-8') as f:
        if not processed_uris: f.write("uri\tdescription\n")
        
        results = g.query(entity_query, initNs={"rdfs": RDFS, "witcher": witcher})
        
        # Filter the full query results to only our target list
        target_results = [row for row in results if str(row.entity) in target_entities]
        total_entities = len(target_results)
        print(f"Processing {total_entities} target entities found in the KG.")
        
        for i, row in enumerate(target_results):
            entity_uri, label, full_text = str(row.entity), str(row.label), str(row.fullText)
            if entity_uri in processed_uris: continue
            
            print(f"Processing Entity {i+1}/{total_entities}: {label}")
            prepared_text = prepare_text_for_summarization(full_text)
            prompt = (f"Summarize the following text about the Witcher 3 entity '{label}' into a single descriptive paragraph of 40–60 words...")
            
            summary = generate_llm_summary(prompt)
            if summary:
                summary = summary.replace('"', '').replace('\n', ' ').strip()
                f.write(f"{entity_uri}\t{summary}\n")
                print(f"  - Summary generated for {label}")
            else:
                print(f"  - FAILED to generate summary for {label}")

    # --- Step 3: Generate Descriptions for TARGET RELATIONS ---
    print("\n--- Generating descriptions for Relations ---")
    print("  - Pre-fetching a sample triple for all properties in the graph...")
    example_query = """
        SELECT ?p (SAMPLE(?s_label) as ?s_label) (SAMPLE(?o_label) as ?o_label)
        WHERE {
            ?s ?p ?o .
            FILTER(isIRI(?o)) # Focus on object properties for better examples
            ?s rdfs:label ?s_label .
            ?o rdfs:label ?o_label .
        }
        GROUP BY ?p
    """
    example_triples_map = {}
    results = g.query(example_query, initNs={"rdfs": RDFS})
    for row in results:
        example_triples_map[str(row.p)] = (str(row.s_label), str(row.o_label))
    print(f"  - Cached examples for {len(example_triples_map)} properties.")
    
    processed_rels = set()
    if os.path.exists(RELATION_DESC_PATH):
        with open(RELATION_DESC_PATH, 'r', encoding='utf-8') as f:
            next(f); [processed_rels.add(line.split('\t')[0]) for line in f]
    print(f"Found {len(processed_rels)} relations already processed. Resuming.")

    with open(RELATION_DESC_PATH, 'a', encoding='utf-8') as f:
        if not processed_rels: f.write("uri\tdescription\n")
        
        results = g.query(relation_query, initNs={"owl": OWL, "rdfs": RDFS})
        total_relations = len(results)
        print(f"Processing {total_relations} target relations.")

        for i, row in enumerate(results):
            rel_uri, label = str(row.rel), str(row.label)

            if rel_uri in processed_rels:
                continue

            print(f"Processing Relation {i+1}/{total_relations}: {label}")

            # --- MODIFICATION: CONTEXT-RICH SPARQL QUERY ---
            # This query now fetches the TYPE of the subject and object
            example_query = """
                SELECT ?s_label ?o_label ?s_type_label ?o_type_label
                WHERE {
                    ?s ?p ?o .
                    ?s rdfs:label ?s_label .
                    ?o rdfs:label ?o_label .
                    
                    # Get the most specific type label available for subject and object
                    OPTIONAL {
                      ?s a ?s_type .
                      ?s_type rdfs:label ?s_type_label .
                      FILTER(!isBlank(?s_type))
                    }
                    OPTIONAL {
                      ?o a ?o_type .
                      ?o_type rdfs:label ?o_type_label .
                      FILTER(!isBlank(?o_type))
                    }
                } LIMIT 1
            """
            example = list(g.query(example_query, initBindings={'p': row.rel}))

            example_text = ""
            if example:
                ex = example[0]
                s_label, o_label = str(ex.s_label), str(ex.o_label)
                # Use the type labels if they were found
                s_type = f" of type '{ex.s_type_label}'" if ex.s_type_label else ""
                o_type = f" of type '{ex.o_type_label}'" if ex.o_type_label else ""
                
                example_text = (
                    f"This relationship connects a subject{s_type} to an object{o_type}. "
                    f"For example, it connects '{s_label}' to '{o_label}'."
                )

            # --- MODIFICATION: CONTEXT-RICH PROMPT ---
            prompt = (
                f"Generate a short, domain-specific, encyclopedic description for the relationship type '{label}' "
                f"from the universe of The Witcher 3. {example_text} "
                f"The description should be a single, concise sentence of about 15-25 words, "
                f"reflecting the specific context if available (e.g., for quests, characters, etc.)."
            )
            
            summary = generate_llm_summary(prompt)
            if summary:
                summary = summary.replace('"', '').replace('\n', ' ').strip()
                f.write(f"{rel_uri}\t{summary}\n")
                print(f"  - Context-Rich Description: {summary}")
            else:
                 print(f"  - FAILED to generate description for {label}")

    print("\nDescription generation complete.")

if __name__ == '__main__':
    process_knowledge_graph()