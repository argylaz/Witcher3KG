import json
import numpy as np
import matplotlib.pyplot as plt
from rdflib import Graph
from tqdm import tqdm
from Hippo_retriever import WitcherHippoRetriever

def run_tuning():
    hippo = WitcherHippoRetriever()
    
    # Load Validation Set
    with open("witcher_val_filtered.json", "r", encoding='utf-8') as f:
        val_questions = json.load(f)

    # Values to test
    damping_values = [0.1, 0.3, 0.5, 0.7, 0.9]
    results = {d: [] for d in damping_values}

    # Load KG once to get Gold Entities from SPARQL
    kg = Graph()
    kg.parse("../RDF/Witcher3KG_Relational.n3", format="n3")

    print(f"[*] Tuning Damping Factor on {len(val_questions)} Validation questions...")

    for item in tqdm(val_questions):
        # 1. Get the target entity label from SPARQL
        gold_labels = []
        try:
            q_res = kg.query(item['sparql_query'])
            for r in q_res:
                name = str(r[0]).split('/')[-1].split('#')[-1].replace('_', ' ').lower()
                gold_labels.append(name)
        except: continue
        
        if not gold_labels: continue

        # 2. Test different damping factors
        for d in damping_values:
            # We bypass the standard retrieve context and do the math here manually
            seed_ids = [hippo.uri_to_id.get(u) for u in item['seed_entities'] if hippo.uri_to_id.get(u) is not None]
            if not seed_ids: continue

            num_nodes = hippo.graph.vcount()
            scores = np.zeros(num_nodes)
            for sid in seed_ids: scores[sid] = 1.0
            
            # 3-step hop
            for _ in range(3):
                new_scores = np.zeros(num_nodes)
                for i in range(num_nodes):
                    if scores[i] > 0:
                        neighbors = hippo.graph.neighbors(i)
                        if neighbors:
                            amt = (scores[i] * d) / len(neighbors)
                            for nb in neighbors: new_scores[nb] += amt
                scores += new_scores

            # Check if any gold label is in the Top 10 nodes found
            top_indices = np.argsort(scores)[::-1][:10]
            retrieved_names = [hippo.passages[str(idx)]['name'].lower() for idx in top_indices]
            
            # Calculate Recall for this damping factor
            success = any(gold in retrieved_names for gold in gold_labels)
            results[d].append(1 if success else 0)

    # 3. Calculate Final Averages
    final_scores = [np.mean(results[d]) for d in damping_values]
    
    # 4. Create the Figure
    plt.figure(figsize=(8, 5))
    plt.plot(damping_values, final_scores, marker='o', linestyle='-', color='b')
    plt.title('Damping Factor vs. Relational Recall (Validation Set)')
    plt.xlabel('Damping Factor (Alpha)')
    plt.ylabel('Recall @ K=10')
    plt.grid(True)
    plt.savefig('damping_tuning_plot.png')
    plt.show()

    print("\n--- TUNING RESULTS ---")
    for d, score in zip(damping_values, final_scores):
        print(f"Alpha {d}: Recall {score:.4f}")

if __name__ == "__main__":
    run_tuning()