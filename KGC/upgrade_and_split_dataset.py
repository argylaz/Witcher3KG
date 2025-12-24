import os
import random
from collections import defaultdict, Counter
from SPARQLWrapper import SPARQLWrapper, JSON

# --- 1. CONFIGURATION ---

# Input/Output Files
INPUT_FILES = ["train.tsv", "valid.tsv", "test.tsv", "all_triples.tsv"] # Will load whatever exists
OUTPUT_DIR = "dataset_v2" # Save new files here to avoid overwriting immediately

# SPARQL Setup
SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
NAMESPACES = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
"""

# --- CLEANING RULES ---
# Map bad/typo relation names to the correct ones
RELATION_FIXES = {
    "http://cgi.di.uoa.gr/witcher/ontology#Region": "http://cgi.di.uoa.gr/witcher/ontology#region",
    "http://cgi.di.uoa.gr/witcher/ontology#Tittles": "http://cgi.di.uoa.gr/witcher/ontology#titles", 
}

# --- DENSIFICATION TARGETS ---
# If a relation has fewer than X triples, fetch more from the KG until X is reached.
# Use the FULL URI of the property.
TARGET_COUNTS = {
    "http://cgi.di.uoa.gr/witcher/ontology#abilities": 100,
    "http://cgi.di.uoa.gr/witcher/ontology#species": 100,
    "http://cgi.di.uoa.gr/witcher/ontology#nationality": 50,
    "http://cgi.di.uoa.gr/witcher/ontology#parents": 50,
    "http://cgi.di.uoa.gr/witcher/ontology#children": 50,
    "http://cgi.di.uoa.gr/witcher/ontology#partner": 30,
    "http://cgi.di.uoa.gr/witcher/ontology#loot": 50, 
}

# --- SPLIT CONFIG ---
VALID_SPLIT = 0.1
TEST_SPLIT = 0.1
MIN_SPLIT_THRESHOLD = 5 # Relations with fewer than this go 100% to Train

# --- HELPER FUNCTIONS ---

def execute_sparql(query):
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(NAMESPACES + query)
    sparql.setReturnFormat(JSON)
    try:
        return sparql.query().convert()["results"]["bindings"]
    except Exception as e:
        print(f"  [!] SPARQL Query failed: {e}")
        return []

def load_existing_triples():
    triples = set()
    for fname in INPUT_FILES:
        if os.path.exists(fname):
            print(f"Loading {fname}...")
            with open(fname, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) == 3:
                        h, r, t = parts
                        # Apply Cleaning Rules Immediately
                        if r in RELATION_FIXES:
                            r = RELATION_FIXES[r]
                        triples.add((h, r, t))
    return triples

def fetch_new_triples(relation_uri, current_count, target_count, existing_triples):
    needed = target_count - current_count
    if needed <= 0:
        return []

    print(f"  -> Fetching ~{needed} new triples for {relation_uri.split('#')[-1]}...")
    
    # Query to get random triples for this relation
    # Note: We fetch more than needed to account for duplicates we already have
    query = f"""
    SELECT DISTINCT ?h ?t WHERE {{
        ?h <{relation_uri}> ?t .
        FILTER(isIRI(?t)) 
    }} LIMIT {needed * 2}
    """
    
    results = execute_sparql(query)
    new_triples = []
    
    for res in results:
        h = res['h']['value']
        t = res['t']['value']
        triple = (h, relation_uri, t)
        
        if triple not in existing_triples:
            new_triples.append(triple)
            # Add to existing set immediately to prevent duplicates in this loop
            existing_triples.add(triple) 
            if len(new_triples) >= needed:
                break
                
    print(f"     Found {len(new_triples)} new unique triples.")
    return new_triples

# --- MAIN LOGIC ---

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 1. Load and Clean
    print("--- Step 1: Loading and Cleaning Data ---")
    all_triples = load_existing_triples()
    print(f"Total unique triples after loading and cleaning: {len(all_triples)}")

    # 2. Analyze and Densify
    print("\n--- Step 2: Analyzing and Densifying ---")
    # Count current relations
    relation_counts = Counter([r for h, r, t in all_triples])
    
    triples_to_add = []
    
    for relation, target in TARGET_COUNTS.items():
        current = relation_counts[relation]
        print(f"Checking {relation.split('#')[-1]}: Current {current} / Target {target}")
        
        if current < target:
            new_data = fetch_new_triples(relation, current, target, all_triples)
            triples_to_add.extend(new_data)
    
    # Add new triples to main list
    for t in triples_to_add:
        all_triples.add(t)
        
    print(f"\nTotal triples after densification: {len(all_triples)}")

    # 3. Stratified Split
    print("\n--- Step 3: Performing Stratified Split ---")
    
    # Group by relation
    triples_by_relation = defaultdict(list)
    for h, r, t in all_triples:
        triples_by_relation[r].append((h, r, t))

    train_set = []
    valid_set = []
    test_set = []

    for relation, triples in triples_by_relation.items():
        rel_name = relation.split('#')[-1]
        
        if len(triples) < MIN_SPLIT_THRESHOLD:
            # Too small to split safely, put all in train
            train_set.extend(triples)
            # print(f"  - {rel_name}: All {len(triples)} -> Train (Sparse)")
        else:
            # Random split
            random.shuffle(triples)
            n_val = max(1, int(len(triples) * VALID_SPLIT))
            n_test = max(1, int(len(triples) * TEST_SPLIT))
            
            # Mathematical safety check
            if len(triples) - n_val - n_test < 1:
                # If dataset is small, prioritize train > test > valid
                n_val = 0
            
            valid_subset = triples[:n_val]
            test_subset = triples[n_val : n_val + n_test]
            train_subset = triples[n_val + n_test :]
            
            train_set.extend(train_subset)
            valid_set.extend(valid_subset)
            test_set.extend(test_subset)
            # print(f"  - {rel_name}: {len(train_subset)} train, {len(valid_subset)} valid, {len(test_subset)} test")

    # 4. Save
    print("\n--- Step 4: Saving Files ---")
    
    def save_file(name, data):
        path = os.path.join(OUTPUT_DIR, name)
        with open(path, 'w', encoding='utf-8') as f:
            for h, r, t in data:
                f.write(f"{h}\t{r}\t{t}\n")
        print(f"Saved {path} ({len(data)} triples)")

    save_file("train.tsv", train_set)
    save_file("valid.tsv", valid_set)
    save_file("test.tsv", test_set)
    save_file("all_triples_combined.tsv", list(all_triples))

    print("\nProcess Complete. You are ready to train.")

if __name__ == "__main__":
    main()