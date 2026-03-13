# analyze_and_combine.py

import os
from collections import Counter

# --- 1. CONFIGURATION ---
MY_TRIPLES_FILE = "accepted_triples.tsv"
COLLEAGUE_TRIPLES_FILE = "accepted_triples_bill.tsv"
COMBINED_OUTPUT_FILE = "all_triples.tsv"

# --- 2. MAIN SCRIPT LOGIC ---
def analyze_and_combine():
    """
    Combines curated triple files, removes duplicates, prints statistics,
    and saves the final combined dataset.
    """
    
    # --- Step 1: Load and Combine Triples ---
    print("Loading and combining triple files...")
    
    all_triples = set() # Use a set to automatically handle duplicates
    
    # Load your file
    if os.path.exists(MY_TRIPLES_FILE):
        with open(MY_TRIPLES_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                # Add the line to the set, stripping any whitespace
                all_triples.add(line.strip())
        print(f"  - Loaded {len(all_triples)} triples from '{MY_TRIPLES_FILE}'.")
    else:
        print(f"Warning: '{MY_TRIPLES_FILE}' not found. Skipping.")

    # Load your colleague's file
    initial_count = len(all_triples)
    if os.path.exists(COLLEAGUE_TRIPLES_FILE):
        with open(COLLEAGUE_TRIPLES_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                all_triples.add(line.strip())
        print(f"  - Loaded triples from '{COLLEAGUE_TRIPLES_FILE}'.")
        print(f"  - Found {len(all_triples) - initial_count} new unique triples.")
    else:
        print(f"Warning: '{COLLEAGUE_TRIPLES_FILE}' not found. Skipping.")
        
    if not all_triples:
        print("Error: No triples were loaded. Aborting.")
        return

    # Convert the set to a list for further processing
    triples_list = [tuple(line.split('\t')) for line in all_triples if len(line.split('\t')) == 3]

    # --- Step 2: Calculate Statistics ---
    print("\nCalculating dataset statistics...")
    
    entities = set()
    relations = set()
    relation_counts = Counter()
    
    for head, relation, tail in triples_list:
        entities.add(head)
        entities.add(tail)
        relations.add(relation)
        relation_counts[relation] += 1
        
    # --- Step 3: Print the Report ---
    print("\n" + "="*50)
    print("--- Curated Knowledge Graph Statistics ---")
    print("="*50)
    print(f"Total Unique Triples:   {len(triples_list)}")
    print(f"Total Unique Entities:  {len(entities)}")
    print(f"Total Unique Relations: {len(relations)}")
    print("-" * 50)
    print("Relation Frequency (Number of instances per property):")
    
    # Sort relations by frequency for a cleaner report
    for relation, count in relation_counts.most_common():
        # Clean up the relation URI for readability
        relation_name = relation.split('#')[-1]
        print(f"  - {relation_name:<25} : {count} triples")
        
    print("="*50)

    # --- Step 4: Save the Combined File ---
    if triples_list:
        print(f"\nSaving combined and deduplicated dataset to '{COMBINED_OUTPUT_FILE}'...")
        # Sort the final list for a consistent output file
        triples_list.sort()
        with open(COMBINED_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            for head, relation, tail in triples_list:
                f.write(f"{head}\t{relation}\t{tail}\n")
        print("Save complete.")
    
if __name__ == "__main__":
    analyze_and_combine()