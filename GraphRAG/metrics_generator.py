import pandas as pd
from rdflib import Graph, RDFS, URIRef
import json
import re
from tqdm import tqdm

# Configurations
RESULTS_CSV = "witcher_hippo_evaluation_results.csv"
KG_PATH = "../RDF/Witcher3KG_Relational.n3"

print("[*] Loading Graph and preparing entity dictionary...")
g = Graph()
g.parse(KG_PATH, format="n3")

# We create a list of all known entity labels to "spot" them in the LLM's text
# This is how we define the 'Predicted Set' from a natural language string
all_entity_labels = set()
for s in g.subjects():
    label = g.value(s, RDFS.label)
    name = str(label) if label else str(s).split('/')[-1].split('#')[-1].replace('_', ' ')
    if len(name) > 3: # Ignore very short strings/noise
        all_entity_labels.add(name.lower())

def calculate_f1(gold_set, pred_set):
    if not gold_set and not pred_set: return 1.0 # Both correctly identified empty result
    if not gold_set or not pred_set: return 0.0
    
    intersection = gold_set.intersection(pred_set)
    precision = len(intersection) / len(pred_set)
    recall = len(intersection) / len(gold_set)
    
    if (precision + recall) == 0: return 0.0
    return 2 * (precision * recall) / (precision + recall)

def run_metrics():
    df = pd.read_csv(RESULTS_CSV)
    scored_results = []

    print(f"[*] Calculating Macro F1 for {len(df)} questions...")
    
    for _, row in tqdm(df.iterrows(), total=len(df)):
        # Get Gold Set from SPARQL
        gold_set = set()
        try:
            q_res = g.query(row['gold_sparql'])
            for r in q_res:
                # Standardize entity name extraction
                val = str(r[0]).split('/')[-1].split('#')[-1].replace('_', ' ').lower()
                gold_set.add(val)
        except: pass

        # Get Predicted Set from LLM Answer (String Matching)
        ans_text = str(row['generated_answer']).lower()
        pred_set = set()
        # Find which known entities the LLM mentioned
        for label in all_entity_labels:
            if label in ans_text:
                pred_set.add(label)
        
        # Calculate F1
        f1 = calculate_f1(gold_set, pred_set)
        
        scored_results.append({
            "template": row['template'],
            "f1": f1
        })

    # Aggregate to get Macro F1
    final_df = pd.DataFrame(scored_results)
    macro_f1_per_template = final_df.groupby('template')['f1'].mean()
    
    print("\n" + "="*30)
    print("   HIPPORAG MACRO F1 RESULTS")
    print("="*30)
    print(macro_f1_per_template)
    print("="*30)
    print(f"Total Mean Macro F1: {final_df['f1'].mean():.4f}")

if __name__ == "__main__":
    run_metrics()