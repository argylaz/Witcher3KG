# test_single_production.py

import json
import argparse
import re
from SPARQLWrapper import SPARQLWrapper, JSON
import time

# Import your final, definitive pipeline class
from pipelines import ExecutionGuidedAgent

# --- 1. SETUP & HELPER FUNCTIONS ---

SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
NAMESPACES = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX geo: <http://www.opengis.net/ont/geosparql#>
    PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
"""

def clean_sparql_string(sparql_query: str) -> str:
    if not sparql_query: return ""
    return sparql_query.replace('\\n', ' ').replace('\\"', '"').strip()

def execute_and_get_bindings(sparql_query: str, is_superlative: bool):
    """Executes a query and returns the raw bindings, or a boolean for ASK."""
    cleaned_query = clean_sparql_string(sparql_query)
    if not cleaned_query or "ERROR" in cleaned_query: return {"error": "Invalid query."}
    full_query = NAMESPACES + cleaned_query
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(full_query)
    sparql.setReturnFormat(JSON)
    try:
        results = sparql.query().convert()
        if "boolean" in results: return {"boolean": results["boolean"]}
        bindings = results["results"]["bindings"]
        if is_superlative and bindings: bindings = [bindings[0]]
        return {"bindings": bindings}
    except Exception as e:
        return {"error": str(e)}

# --- NEW: Final, robust F1 calculation logic ---
def find_label_variable(sparql_query: str) -> str:
    """Heuristically finds the variable that holds the human-readable name."""
    # Look for variables commonly used for labels or names
    match = re.search(r'SELECT.*?(\?(?:[a-zA-Z]*[Ll]abel|[a-zA-Z]*[Nn]ame))\b', sparql_query, re.IGNORECASE)
    if match:
        return match.group(1).replace('?', '')
    
    # Fallback: if no typical label name, use the first variable
    first_var_match = re.search(r'SELECT\s+(?:DISTINCT\s+)?(\?\w+)', sparql_query, re.IGNORECASE)
    if first_var_match:
        return first_var_match.group(1).replace('?', '')
    return None


def calculate_label_f1_score(gen_bindings: list, gt_bindings: list, gen_query: str, gt_query: str):
    """
    Calculates F1 by comparing the sets of values from the 'label' variable in each result.
    """
    if not isinstance(gen_bindings, list) or not isinstance(gt_bindings, list):
        return 0.0

    # Find the specific label variable for each query
    gt_label_key = find_label_variable(gt_query)
    gen_label_key = find_label_variable(gen_query)

    if not gt_label_key or not gen_label_key:
        return 0.0 # Cannot perform comparison without a label variable

    # Extract the sets of label values
    gt_answers = {row[gt_label_key]['value'] for row in gt_bindings if gt_label_key in row}
    gen_answers = {row[gen_label_key]['value'] for row in gen_bindings if gen_label_key in row}
    
    if not gen_answers and not gt_answers: return 1.0

    true_positives = len(gen_answers.intersection(gt_answers))
    false_positives = len(gen_answers.difference(gt_answers))
    false_negatives = len(gt_answers.difference(gen_answers))
    
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    return f1

# --- 2. DEFINE YOUR TEST CASES HERE ---
TEST_CASES = [
    {
        "question": "What's the strongest sword in the witcher 3 game?",
        "ground_truth_sparql": "SELECT ?subjectLabel WHERE { ?subject witcher:abilities dbr:Signs . ?subject rdfs:label ?subjectLabel . }",
        "template_id": "T6_PropertyLookup"
    },
    # Add more test cases here
]

def main():
    parser = argparse.ArgumentParser(description="Test and evaluate the Execution-Guided Agent.")
    parser.add_argument("--api-key", required=True, help="Your DeepSeek API key.")
    args = parser.parse_args()

    print("Initializing pipeline...")
    pipeline_c = ExecutionGuidedAgent(api_key=args.api_key)
    print("Pipeline initialized.")

    for i, test_case in enumerate(TEST_CASES):
        print("\n" + "="*20, f"Running Test Case {i+1}", "="*20)
        
        question = test_case["question"]
        ground_truth_sparql = test_case["ground_truth_sparql"]
        template_id = test_case["template_id"]
        
        print(f"USER QUESTION: \"{question}\"")
        print("Generating SPARQL query...")
        
        generated_sparql = ""
        try:
            generated_sparql = pipeline_c.generate_query(question)
        except Exception as e:
            print(f"\n--- Pipeline C CRASHED --- \nError: {e}")
            continue

        # --- Execute and Evaluate ---
        is_superlative = template_id in ['T2_ProximitySearch', 'T11_SuperlativeByAttribute']
        
        ground_truth_results = execute_and_get_bindings(ground_truth_sparql, is_superlative)
        generated_results = execute_and_get_bindings(generated_sparql, is_superlative)
        
        # --- Execution Accuracy ---
        # For EA, we still need a strict row comparison. We'll build the canonical rows here.
        gt_rows = {json.dumps(row, sort_keys=True) for row in ground_truth_results.get("bindings", [])}
        gen_rows = {json.dumps(row, sort_keys=True) for row in generated_results.get("bindings", [])}
        is_correct_ea = (
            "error" not in generated_results and "error" not in ground_truth_results and
            gen_rows == gt_rows
        )
        
        # --- F1 Score (Label-Centric) ---
        f1 = 0.0
        if "boolean" in ground_truth_results:
            f1 = 1.0 if generated_results.get("boolean") == ground_truth_results.get("boolean") else 0.0
        else:
            f1 = calculate_label_f1_score(
                generated_results.get("bindings", []),
                ground_truth_results.get("bindings", []),
                generated_sparql,
                ground_truth_sparql
            )

        # --- Print Final Report ---
        print("\n" + "-"*20, "Evaluation Report", "-"*20)
        print("\n--- Ground-Truth SPARQL ---")
        print(ground_truth_sparql)
        print("\n--- Generated SPARQL ---")
        print(generated_sparql)
        print("\n--- METRICS ---")
        print(f"  - Execution Accuracy: {'CORRECT' if is_correct_ea else 'INCORRECT'}")
        print(f"  - Label F1-Score: {f1:.4f}")
        print("-" * 50)

if __name__ == "__main__":
    main()