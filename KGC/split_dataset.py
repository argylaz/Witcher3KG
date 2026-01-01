# split_dataset.py
import os
import random
from collections import defaultdict

# --- 1. CONFIGURATION ---
COMBINED_FILE = "all_triples.tsv"
TRAIN_FILE = "train.tsv"
VALID_FILE = "valid.tsv"
TEST_FILE = "test.tsv"

VALID_SPLIT = 0.1  # 10%
TEST_SPLIT = 0.1   # 10%

# Any relation with this many triples or fewer will NOT be split.
# It will be placed entirely in the training set.
MIN_SPLIT_THRESHOLD = 5 # A reasonable threshold

# --- 2. MAIN SCRIPT LOGIC ---
def stratified_split():
    print(f"Loading combined triples from '{COMBINED_FILE}'...")
    if not os.path.exists(COMBINED_FILE):
        print("Error: Combined file not found. Please run 'analyze_and_combine.py' first.")
        return

    with open(COMBINED_FILE, 'r', encoding='utf-8') as f:
        all_triples = [line.strip() for line in f.readlines()]

    # --- Step 1: Group triples by relation ---
    triples_by_relation = defaultdict(list)
    for line in all_triples:
        try:
            h, r, t = line.split('\t')
            triples_by_relation[r].append((h, r, t))
        except ValueError:
            print(f"Warning: Skipping malformed line: {line}")
            continue
            
    print(f"Found {len(triples_by_relation)} unique relations.")

    # --- Step 2: Perform the stratified split ---
    train_triples = []
    valid_triples = []
    test_triples = []
    
    print("Performing stratified split by relation...")
    for relation, triples in triples_by_relation.items():
        relation_name = relation.split('#')[-1]
        
        # If the relation group is too small, add all to training
        if len(triples) < MIN_SPLIT_THRESHOLD:
            print(f"  - Relation '{relation_name}' has only {len(triples)} triples. Adding all to training set.")
            train_triples.extend(triples)
            continue
        
        # If large enough, perform the split
        random.shuffle(triples)
        
        num_valid = int(len(triples) * VALID_SPLIT)
        num_test = int(len(triples) * TEST_SPLIT)
        
        # Ensure at least one triple for valid and test if possible
        num_valid = max(1, num_valid)
        num_test = max(1, num_test)
        
        valid_set = triples[:num_valid]
        test_set = triples[num_valid : num_valid + num_test]
        train_set = triples[num_valid + num_test :]
        
        train_triples.extend(train_set)
        valid_triples.extend(valid_set)
        test_triples.extend(test_set)
        
        print(f"  - Splitting '{relation_name}' ({len(triples)} triples): {len(train_set)} train, {len(valid_set)} valid, {len(test_set)} test.")

    # --- Step 3: Save the final files ---
    def save_to_tsv(filename, triples_to_save):
        with open(filename, 'w', encoding='utf-8') as f:
            for h, r, t in triples_to_save:
                f.write(f"{h}\t{r}\t{t}\n")
    
    print("\nSaving final dataset files...")
    save_to_tsv(TRAIN_FILE, train_triples)
    save_to_tsv(VALID_FILE, valid_triples)
    save_to_tsv(TEST_FILE, test_triples)

    print("\n--- Split Summary ---")
    print(f"Total Triples: {len(all_triples)}")
    print(f"Training Set:  {len(train_triples)} triples ({len(train_triples)/len(all_triples):.1%})")
    print(f"Validation Set: {len(valid_triples)} triples ({len(valid_triples)/len(all_triples):.1%})")
    print(f"Test Set:      {len(test_triples)} triples ({len(test_triples)/len(all_triples):.1%})")
    print("\nDataset split complete.")

if __name__ == "__main__":
    stratified_split()