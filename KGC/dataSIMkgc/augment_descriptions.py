import os
import time
import re
from rdflib import Graph, Namespace, RDF, RDFS, URIRef
import requests
import json
import glob

# --- Configuration ---
OPENROUTER_API_KEY = ""

# The graph is our source of truth for text
KG_FULL_PATH = '../../RDF/Witcher3KG_full.ttl' 

# The SimKGC dataset files define our scope
SIMKGC_DATA_DIR = './dataset_simkgc' # The folder with train.jsonl, etc.

# The description file to read from AND append to
ENTITY_DESC_PATH = '../entity_desc.tsv'

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

# --- Replace your existing function with this DEFINITIVE version ---
def generate_llm_summary(prompt_text, max_retries=3):
    """
    Sends a prompt to the LLM using the high-priority paid tier with robust retries.
    """
    time.sleep(0.5) # A small, polite delay
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
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers, data=json.dumps(data_payload), timeout=60
            )

            # Check for specific HTTP errors
            if response.status_code == 402:
                print("!!! FATAL HTTP Error 402: Payment Required. !!!")
                print("Your account balance is likely depleted. Please check your OpenRouter dashboard.")
                return None # Hard stop on payment errors
            
            response.raise_for_status() # Raise exceptions for other errors (like 429, 500)
            
            summary = response.json()['choices'][0]['message']['content'].strip()
            return summary

        except requests.exceptions.HTTPError as http_err:
            print(f"  - HTTP Error (attempt {attempt+1}/{max_retries}): {http_err} - Retrying...")
            wait_time = 5 * (2 ** attempt)
            time.sleep(wait_time)
        except Exception as e:
            print(f"  - Unexpected error (attempt {attempt+1}/{max_retries}): {e} - Retrying...")
            time.sleep(5)
            
    print("  - FAILED to get a response after all retries.")
    return None

# --- Main Augmentation Logic ---
def augment_entity_descriptions():
    
    # --- Step 1: Load all entities that are mentioned in the SimKGC dataset ---
    print(f"--- Step 1: Building universe of all entities from SimKGC files in '{SIMKGC_DATA_DIR}' ---")
    
    universe_entities = set()
    jsonl_files = glob.glob(os.path.join(SIMKGC_DATA_DIR, '*.jsonl'))
    if not jsonl_files:
        print(f"!!! FATAL ERROR: No .jsonl files found in '{SIMKGC_DATA_DIR}'. !!!")
        return
        
    for file_path in jsonl_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                universe_entities.add(data['head'])
                universe_entities.add(data['tail'])
                for tail_entity in data.get('tails', []):
                    universe_entities.add(tail_entity)
    
    print(f"  - Found {len(universe_entities)} unique entities across all SimKGC splits.")

    # --- Step 2: Load the URIs of entities we already have descriptions for ---
    processed_uris = set()
    if os.path.exists(ENTITY_DESC_PATH):
        with open(ENTITY_DESC_PATH, 'r', encoding='utf-8') as f:
            next(f) # Skip header
            for line in f:
                processed_uris.add(line.split('\t')[0])
    print(f"  - Found {len(processed_uris)} entities with existing descriptions in '{ENTITY_DESC_PATH}'.")

    # --- Step 3: Calculate the "Delta" - the entities we need to process ---
    entities_to_process = list(universe_entities - processed_uris)
    print(f"  - Calculated a delta of {len(entities_to_process)} new entities that need descriptions.")
    if not entities_to_process:
        print("\nAll entities required for SimKGC already have descriptions. Nothing to do.")
        return

    # --- Step 4: Load the main KG to get the full text for the missing entities ---
    g = Graph()
    print(f"\nLoading full knowledge graph from {KG_FULL_PATH} to fetch text...")
    g.parse(KG_FULL_PATH, format='turtle')
    print("  - Graph loaded.")

    # --- Step 5: Process only the missing entities ---
    print(f"\n--- Generating descriptions for {len(entities_to_process)} missing entities ---")
    with open(ENTITY_DESC_PATH, 'a', encoding='utf-8') as f: # Open in append mode
        for i, entity_uri_str in enumerate(entities_to_process):
            entity_uri = URIRef(entity_uri_str)
            
            label = g.value(entity_uri, RDFS.label)
            full_text = g.value(entity_uri, witcher.hasFullText)

            if not label or not full_text:
                print(f"  - WARNING: Skipping {entity_uri_str} - missing label or fullText in KG.")
                continue

            print(f"Processing Missing Entity {i+1}/{len(entities_to_process)}: {label}")
            
            prepared_text = prepare_text_for_summarization(str(full_text))
            prompt = (f"Summarize the following text about the Witcher 3 entity '{label}' into a single descriptive paragraph of 40–60 words...")
            
            summary = generate_llm_summary(prompt)
            if summary:
                summary = summary.replace('"', '').replace('\n', ' ').strip()
                f.write(f"{entity_uri_str}\t{summary}\n")
                print(f"  - Appended summary for {label}")
            else:
                print(f"  - FAILED to generate summary for {label}")

    print("\nDescription augmentation complete.")

if __name__ == '__main__':
    augment_entity_descriptions()