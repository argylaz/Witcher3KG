import os
import time
import re
from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef
import requests
import json
import glob

# --- Configuration ---
OPENROUTER_API_KEY = "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"

# The graph the version of the graph that contains the full text descriptions
KG_FULL_PATH = '../RDF/Witcher3KG_full.ttl' 

# The KGC dataset files
KGC_DATASET_DIR = './dataset_v3/'

# Output files
ENTITY_DESC_PATH = 'entity_desc.tsv'
RELATION_DESC_PATH = 'relation_desc.tsv'

# --- Namespaces ---
witcher = Namespace("http://cgi.di.uoa.gr/witcher/ontology#")
dbr = Namespace("http://cgi.di.uoa.gr/witcher/resource/")

# Model
MODEL_NAME = "qwen/qwen3-4b:free" 

# --- Helper Functions ---
def prepare_text_for_summarization(full_text: str):
    MAX_CHARS = 150000
    if len(full_text) <= MAX_CHARS: return full_text
    print(f"  - WARNING: Text extremely long ({len(full_text)} chars). Truncating.")
    return (full_text[:75000] + "\n\n--- [CONTENT TRUNCATED] ---\n\n" + full_text[-75000:])


def generate_llm_summary(prompt_text, max_retries=4): # Increased retries to 4
    """
    Sends a prompt to the LLM with robust error handling, a universal delay,
    and aggressive exponential backoff for rate limiting.
    """
    
    # ALWAYS wait before making a request
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
            
            return summary
            
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

# --- Helper to get target URIs ---
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
    print("\n--- Generating descriptions for KGC Relations ---")

    # --- Pre-fetch a sample triple's TYPE information for all properties ---
    print("  - Pre-fetching sample type information for all properties...")
    example_query = """
        SELECT ?p 
               (SAMPLE(?s_type_label) as ?s_type_label)
               (SAMPLE(?o_type_label) as ?o_type_label)
        WHERE {
            ?s ?p ?o .
            FILTER(isIRI(?o))
            # Get the most specific type label available
            OPTIONAL {
              ?s a ?s_type .
              ?s_type rdfs:label ?s_type_label .
              FILTER(!isBlank(?s_type) && ?s_type != owl:NamedIndividual)
            }
            OPTIONAL {
              ?o a ?o_type .
              ?o_type rdfs:label ?o_type_label .
              FILTER(!isBlank(?o_type) && ?o_type != owl:NamedIndividual)
            }
        }
        GROUP BY ?p
    """
    example_types_map = {}
    results = g.query(example_query, initNs={"rdfs": RDFS, "owl": OWL})
    for row in results:
        example_types_map[str(row.p)] = {
            "s_type": str(row.s_type_label) if row.s_type_label else "entity",
            "o_type": str(row.o_type_label) if row.o_type_label else "entity"
        }
    print(f"  - Cached type contexts for {len(example_types_map)} properties.")
    
    processed_rels = set()
    if os.path.exists(RELATION_DESC_PATH):
        with open(RELATION_DESC_PATH, 'r', encoding='utf-8') as f:
            next(f); [processed_rels.add(line.split('\t')[0]) for line in f]
    print(f"Found {len(processed_rels)} relations already processed. Resuming.")

    with open(RELATION_DESC_PATH, 'a', encoding='utf-8') as f:
        if not processed_rels: f.write("uri\tdescription\n")
        
        results = g.query(example_query, initNs={"owl": OWL, "rdfs": RDFS})
        total_relations = len(results)
        print(f"Processing {results} target relations.")

       
        for i, rel_uri_str in enumerate(sorted(list(target_relations))):
            if rel_uri_str in processed_rels: continue
            
            rel_uri = URIRef(rel_uri_str)
            label = str(g.value(rel_uri, RDFS.label, default=rel_uri_str.split('#')[-1]))
            print(f"Processing Relation {i+1}/{total_relations}: {label}")

            #  Use TYPE context, not INSTANCE context
            context_text = ""
            if rel_uri_str in example_types_map:
                ex = example_types_map[rel_uri_str]
                # Provide the types of the subject and object for context
                context_text = f"This relationship connects a subject of type '{ex['s_type']}' to an object of type '{ex['o_type']}'."
            
            prompt = f"""
                      Your role is to act as an ontologist documenting a knowledge graph for The Witcher 3 universe.
                      Your task is to write a short, general, and reusable description for the relationship type provided below.

                      The description must be a single, concise sentence that explains the general meaning of the relationship based on the types of things it connects. Do not use specific examples.

                      --- CONTEXT ---
                      Relationship Name: {label}
                      Context: {context_text}
                      --- END CONTEXT ---

                      Description:
                      """
        
            summary = generate_llm_summary(prompt)
            if summary:
                summary = summary.replace('"', '').replace('\n', ' ').strip()
                f.write(f"{rel_uri_str}\t{summary}\n")
                print(f"  - Generated Description: {summary}")
            else:
                 print(f"  - FAILED to generate description for {label}")

    print("\nDescription generation complete.")

if __name__ == '__main__':
    process_knowledge_graph()