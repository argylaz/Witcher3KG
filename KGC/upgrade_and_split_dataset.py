import os
import random
from collections import defaultdict
import pandas as pd # Using pandas for easier data handling

# SPARQL Setup
SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
NAMESPACES = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
"""


# --- 1. CONFIGURATION ---
# The combined curated tipples file from the previous curation step
CURATED_FILE_PATH = 'dataset_v2/all_triples_combined.tsv' 
OUTPUT_DIR = "dataset_v3" # New version for a clean slate

# --- RELATION MERGING RULES ---
# Define the new, unified relation
UNIFIED_FAMILY_RELATION = "http://cgi.di.uoa.gr/witcher/ontology#family_relationship"
# Define which relations should be merged into it
RELATIONS_TO_MERGE = {
    "http://cgi.di.uoa.gr/witcher/ontology#parents",
    "http://cgi.di.uoa.gr/witcher/ontology#children",
    "http://cgi.di.uoa.gr/witcher/ontology#relative",
    "http://cgi.di.uoa.gr/witcher/ontology#family",
}

# --- SPLIT CONFIG ---
VALID_SPLIT = 0.1
TEST_SPLIT = 0.1
MIN_SPLIT_THRESHOLD = 5

# --- MAIN LOGIC ---
def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # --- Step 1: Load the single, complete, curated dataset ---
    print(f"--- Step 1: Loading curated triples from {CURATED_FILE_PATH} ---")
    try:
        df = pd.read_csv(CURATED_FILE_PATH, sep='\t', header=None, names=['head', 'relation', 'tail'])
        all_triples = [tuple(x) for x in df.to_numpy()]
        print(f"  - Successfully loaded {len(all_triples)} curated triples.")
    except FileNotFoundError:
        print(f"!!! FATAL ERROR: Curated file not found at '{CURATED_FILE_PATH}'. Please run previous scripts first. !!!")
        return
    except Exception as e:
        print(f"!!! FATAL ERROR: Could not read the curated file. Error: {e} !!!")
        return

    # --- Step 1.5: Merge Family Relations ---
    print("\n--- Step 1.5: Merging family-related relations ---")
    merged_triples = []
    merge_count = 0
    for h, r, t in all_triples:
        if r in RELATIONS_TO_MERGE:
            merged_triples.append((h, UNIFIED_FAMILY_RELATION, t))
            merge_count += 1
        else:
            merged_triples.append((h, r, t))
    print(f"  - Merged {merge_count} triples into the unified '{UNIFIED_FAMILY_RELATION.split('#')[-1]}' relation.")
    print(f"  - Total triples after merging: {len(merged_triples)}")
    
    # All subsequent steps will now use the `merged_triples` list
    all_triples = merged_triples

    # --- Step 2: Isolate the Geralt tripples from the curated set ---
    geralt_uri_string = "http://cgi.di.uoa.gr/witcher/resource/Geralt_of_Rivia"
    print(f"\n--- Step 2: Isolating Geralt of Rivia case study (subject only) ---")
    
    geralt_triples = []
    other_triples = []
    for h, r, t in all_triples:
        if str(h) == geralt_uri_string: # Ensure we are comparing strings
            geralt_triples.append((h, r, t))
        else:
            other_triples.append((h, r, t))
            
    print(f"  - Isolated {len(geralt_triples)} triples with Geralt as the subject.")
    print(f"  - {len(other_triples)} triples remain for train/valid split.")

    # --- Step 3: Stratified Split on the Non-Geralt Data ---
    print("\n--- Step 3: Performing Stratified Split on the remaining triples ---")
    triples_by_relation = defaultdict(list)
    for h, r, t in other_triples:
        triples_by_relation[r].append((h, r, t))

    train_set = []
    valid_set = []
    test_set = [] # This will be the non-Geralt part of the test set

    for relation, triples in triples_by_relation.items():
        if len(triples) < MIN_SPLIT_THRESHOLD:
            train_set.extend(triples)
        else:
            random.shuffle(triples)
            n_val = max(1, int(len(triples) * VALID_SPLIT))
            n_test = max(1, int(len(triples) * TEST_SPLIT))
            if len(triples) - n_val - n_test < 1: n_val = 0
            
            valid_set.extend(triples[:n_val])
            test_set.extend(triples[n_val : n_val + n_test])
            train_set.extend(triples[n_val + n_test :])

    # --- Step 4: Augment the Test Set with Geralt tripples ---
    print(f"\n--- Step 4: Augmenting test set with {len(geralt_triples)} Geralt triples... ---")
    test_set.extend(geralt_triples)

    # --- Step 5: Save Files ---
    print("\n--- Step 5: Saving Files ---")
    
    def save_file(name, data):
        path = os.path.join(OUTPUT_DIR, name)
        # Convert to DataFrame for easy, standardized saving
        df_to_save = pd.DataFrame(data, columns=['head', 'relation', 'tail'])
        df_to_save.sort_values(by=['head', 'relation', 'tail'], inplace=True)
        df_to_save.to_csv(path, sep='\t', header=False, index=False)
        print(f"Saved {path} ({len(data)} triples)")

    save_file("train.tsv", train_set)
    save_file("valid.tsv", valid_set)
    save_file("test.tsv", test_set)
    
    print("\nProcess Complete. You are ready to train.")
    print("\nFinal Split Counts:")
    print(f"  - Train: {len(train_set)} triples")
    print(f"  - Valid: {len(valid_set)} triples")
    print(f"  - Test:  {len(test_set)} triples (now includes the subject-only Geralt case study)")

if __name__ == "__main__":
    main()