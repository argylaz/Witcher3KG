import json
import os
import time
import pandas as pd
from tqdm import tqdm
from Hippo_retriever import WitcherHippoRetriever

# --- CONFIGURATION ---
TEST_SET_FILE = "witcher_test_filtered.json"
RESULTS_CSV = "witcher_hippo_evaluation_results_09.csv"
RESULTS_JSON = "witcher_hippo_evaluation_results_09.json"

def run_evaluation():
    # Initialize Retriever
    hippo = WitcherHippoRetriever()
    
    # Load the benchmark
    with open(TEST_SET_FILE, 'r', encoding='utf-8') as f:
        questions = json.load(f)
    
    print(f"[*] Starting evaluation on {len(questions)} questions...")
    results = []

    # Loop through questions
    for item in tqdm(questions):
        q_id = item['query_id']
        question = item['question']
        gold_sparql = item['sparql_query']
        
        start_time = time.time()
        
        # Phase A: Graph Retrieval
        try:
            context = hippo.retrieve_context(question)
            retrieval_success = True if context else False
        except Exception as e:
            print(f"\n[!] Retrieval Error on {q_id}: {e}")
            context = ""
            retrieval_success = False

        # Phase B: Answer Generation
        if retrieval_success:
            # We add a small delay to respect rate limits
            time.sleep(1.5) 
            answer = hippo.generate_answer(question, context)
        else:
            answer = "N/A - Retrieval Failed"
        
        latency = time.time() - start_time

        # 4. Record Data
        results.append({
            "query_id": q_id,
            "template": item['template_id'],
            "question": question,
            "retrieval_success": retrieval_success,
            "generated_answer": answer,
            "gold_sparql": gold_sparql,
            "latency": round(latency, 2)
        })

        # Save progress incrementally
        with open(RESULTS_JSON, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
            
    # 5. Final Export to CSV
    df = pd.DataFrame(results)
    df.to_csv(RESULTS_CSV, index=False, encoding='utf-8-sig')
    
    print(f"\n[!] Evaluation Complete!")
    print(f"Results saved to {RESULTS_CSV}")

if __name__ == "__main__":
    run_evaluation()