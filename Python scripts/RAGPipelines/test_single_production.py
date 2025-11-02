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

def extract_answer_keys(sparql_query: str) -> list:
    """
    Intelligently finds the primary "answer" variable from a SELECT clause.
    It prioritizes variables that look like labels or names.
    """
    select_clause_match = re.search(r'SELECT\s+(.*?)\s+WHERE', sparql_query, re.IGNORECASE | re.DOTALL)
    if not select_clause_match:
        return []
    
    select_vars_str = select_clause_match.group(1)
    
    # Find all variables in the select clause
    all_variables = re.findall(r'(\?\w+)', select_vars_str)
    if not all_variables:
        return []

    # Prioritize any variable that contains 'label' or 'name'
    for var in all_variables:
        if 'label' in var.lower() or 'name' in var.lower():
            # Found the semantic answer, return only this key
            return [var.replace('?', '')]
            
    # For comparative queries, the answer is often named '?result'
    if 'AS ?result' in select_vars_str.upper():
        return ['result']

    # Fallback: if no label/name variable is found, return only the first variable
    return [all_variables[0].replace('?', '')]

def execute_and_get_results(sparql_query: str, is_superlative: bool):
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
        canonical_rows = {json.dumps(row, sort_keys=True) for row in bindings}
        return {"rows": canonical_rows, "bindings": bindings}
    except Exception as e:
        return {"error": str(e)}

# --- NEW: Final, robust F1 calculation function ---
def calculate_f1_score(gen_bindings: list, gt_bindings: list, gen_keys: list, gt_keys: list):
    """
    Calculates F1 by comparing the sets of all values in the answer key columns.
    This is robust to different variable names.
    """
    if not isinstance(gen_bindings, list) or not isinstance(gt_bindings, list):
        return 0.0
    
    # Extract all values from all answer key columns for each result set
    gt_answers = {val['value'] for row in gt_bindings for key in gt_keys if key in row for val in [row[key]]}
    gen_answers = {val['value'] for row in gen_bindings for key in gen_keys if key in row for val in [row[key]]}
    
    if not gen_answers and not gt_answers: return 1.0

    true_positives = len(gen_answers.intersection(gt_answers))
    false_positives = len(gen_answers.difference(gt_answers))
    false_negatives = len(gt_answers.difference(gen_answers))
    
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    return f1


# --- 2. TEST CASES ---
TEST_CASES = [
    {
        "question": "Is there a road that connects Blackbough and Midscope?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Blackbough> geo:hasGeometry/geo:asWKT ?geomA. <http://cgi.di.uoa.gr/witcher/resource/Midscope> geo:hasGeometry/geo:asWKT ?geomB. ?path a witcher:Road ; geo:hasGeometry/geo:asWKT ?pathGeom . FILTER(geof:sfIntersects(?pathGeom, ?geomA) && geof:sfIntersects(?pathGeom, ?geomB)) }",
        "template_id": "T1_SpatialRelationship"
    },
    {
        "question": "What is the closest Signaling Stake to Call of the Wild?",
        "ground_truth_sparql": "SELECT ?featureALabel (geof:distance(?wktA, ?wktB) AS ?distance) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Call_of_the_Wild> geo:hasGeometry/geo:asWKT ?wktB . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#SignalingStake> ; rdfs:label ?featureALabel ; geo:hasGeometry/geo:asWKT ?wktA . } ORDER BY ASC(?distance) LIMIT 1",
        "template_id": "T2_ProximitySearch"
    },
    {
        "question": "Which map is Distillery in?",
        "ground_truth_sparql": "SELECT ?mapLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Distillery> witcher:isPartOf <http://cgi.di.uoa.gr/witcher/resource/Skellige_Map> . <http://cgi.di.uoa.gr/witcher/resource/Skellige_Map> rdfs:label ?mapLabel . }",
        "template_id": "T3_LocationContextDiscovery",
    },
    {
        "question": "Is the Merchant with Arachis Pin located within the Velen/Novigrad Map?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad_Merchant_with_Arachis_Pin_680p0_2016p0> geo:hasGeometry/geo:asWKT ?geomA_WKT . <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad_Map> geo:hasGeometry/geo:asWKT ?geomB_WKT . FILTER(geof:sfWithin(?geomA_WKT, ?geomB_WKT)) }",
        "template_id": "T4_GeospatialVerification"
    },
    {
        "question": "Which entities have |appears_games = as their abilities?",
        "ground_truth_sparql": "SELECT ?subjectLabel WHERE { ?subject <http://cgi.di.uoa.gr/witcher/ontology#abilities> \"|appears_games =\" . ?subject rdfs:label ?subjectLabel . }",
        "template_id": "T6_PropertyLookup_Inverse"
    },
    {
        "question": "Which entities have the sign ability?",
        "ground_truth_sparql": "SELECT ?subjectLabel WHERE {  ?subject witcher:abilities dbr:Signs . ?subject rdfs:label ?subjectLabel . }",
        "template_id": "T5_PropertyLookup"
    },
    {
        "question": "What are the alternative names (aka) of entities that have the race Human?",
        "ground_truth_sparql": "SELECT DISTINCT ?targetValueLabel WHERE { ?member <http://cgi.di.uoa.gr/witcher/ontology#race> <http://cgi.di.uoa.gr/witcher/resource/Human> . ?member <http://cgi.di.uoa.gr/witcher/ontology#aka> ?targetValue . OPTIONAL { ?targetValue rdfs:label ?label . } BIND(IF(isURI(?targetValue), ?label, ?targetValue) AS ?targetValueLabel) }",
        "template_id": "T7_MultiHopQuery"
    },
    {
        "question": "Which Mappin entities in Blackbough have the in-game coordinates xy(-225.0,168.0)?",
        "ground_truth_sparql": "SELECT ?entityLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Blackbough> geo:hasGeometry/geo:asWKT ?polygonWKT . ?entity a <http://cgi.di.uoa.gr/witcher/ontology#Mappin> ; <http://cgi.di.uoa.gr/witcher/ontology#hasInGameCoordinates> \"xy(-225.0,168.0)\" ; rdfs:label ?entityLabel ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }",
        "template_id": "T8_ComposedQuery"
    },
    {
        "question": "How many Side Quests are in Claywitch?",
        "ground_truth_sparql": "SELECT (COUNT(?feature) as ?count) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Claywitch> geo:hasGeometry/geo:asWKT ?polygonWKT . ?feature a <http://cgi.di.uoa.gr/witcher/ontology#SideQuest> ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }",
        "template_id": "T9_SpatialCounting"
    },
    {
        "question": "Does Velen/Novigrad Map have more Plegmund than Oxenfurt Outskirts?",
        "ground_truth_sparql": "SELECT (IF(?countA > ?countB, \"Yes\", \"No\") AS ?result) WHERE { { SELECT (COUNT(?featureA) as ?countA) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad_Map> geo:hasGeometry/geo:asWKT ?polyA . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#Plegmund> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polyA)) } } { SELECT (COUNT(?featureB) as ?countB) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Oxenfurt_Outskirts> geo:hasGeometry/geo:asWKT ?polyB . ?featureB a <http://cgi.di.uoa.gr/witcher/ontology#Plegmund> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polyB)) } } }",
        "template_id": "T10_ComparativeCounting",
    },
    {
        "question": "What is the highest value Blood and Wine quest item?",
        "ground_truth_sparql": "SELECT ?featureLabel ?value WHERE { ?feature a <http://cgi.di.uoa.gr/witcher/ontology#Blood_and_Wine_quest_items> ; rdfs:label ?featureLabel ; <http://cgi.di.uoa.gr/witcher/ontology#value> ?value . } ORDER BY DESC(?value) LIMIT 1",
        "template_id": "T11_SuperlativeByAttribute"
    },
    {
        "question": "What is the broader category that Nilfgaardians belong to?",
        "ground_truth_sparql": "SELECT ?parentClassLabel WHERE { <http://cgi.di.uoa.gr/witcher/ontology#Nilfgaardians> rdfs:subClassOf ?parentClass . FILTER(isIRI(?parentClass)) ?parentClass rdfs:label ?parentClassLabel . }",
        "template_id": "T12_SchemaLookup",
    },
    {
        "question": "Which location has either a Gwent Seller or a Harbor at the Inn at the Crossroads?",
        "ground_truth_sparql": "SELECT DISTINCT ?locationLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Inn_at_the_Crossroads> rdfs:label ?locationLabel ; geo:hasGeometry/geo:asWKT ?polygonWKT . FILTER ( EXISTS { ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#GwentSeller> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polygonWKT)) } || EXISTS { ?featureB a <http://cgi.di.uoa.gr/witcher/ontology#Harbor> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polygonWKT)) } ) }",
        "template_id": "T13_FindLocationByFeatureCombination",
    },
    {
        "question": "List all known The Lady of the Lake characters.",
        "ground_truth_sparql": "SELECT ?instanceLabel WHERE { ?instance a <http://cgi.di.uoa.gr/witcher/ontology#The_Lady_of_the_Lake_characters> . ?instance rdfs:label ?instanceLabel . }",
        "template_id": "T14_InstanceListingByClass",
    },
    {
        "question": "Is there a road that connects Claywitch and Blackbough?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Claywitch> geo:hasGeometry/geo:asWKT ?geomA. <http://cgi.di.uoa.gr/witcher/resource/Blackbough> geo:hasGeometry/geo:asWKT ?geomB. ?path a witcher:Road ; geo:hasGeometry/geo:asWKT ?pathGeom . FILTER(geof:sfIntersects(?pathGeom, ?geomA) && geof:sfIntersects(?pathGeom, ?geomB)) }",
        "template_id": "T15_PathVerification",
    }
    # {
    #     "question": "What's the strongest sword in the witcher 3 game?",
    #     "ground_truth_sparql": "SELECT ?subjectLabel WHERE { ?subject <http://cgi.di.uoa.gr/witcher/ontology#eye_color> \"Brown\" . ?subject rdfs:label ?subjectLabel . }",
    #     "template_id": "T6_PropertyLookup_Inverse"
    # },
    # {
    #     "question": "What is the name of Geralt's horse?",
    #     "ground_truth_sparql": "SELECT ?instanceLabel WHERE { ?instance a <http://cgi.di.uoa.gr/witcher/ontology#Gangs> . ?instance rdfs:label ?instanceLabel . }",
    #     "template_id": "T14_InstanceListingByClass",
    # },
    # {
    #     "question": "Which characters in The Witcher universe are male?",
    #     "ground_truth_sparql": "SELECT ?subjectLabel WHERE { ?subject <http://cgi.di.uoa.gr/witcher/ontology#gender> \"Male\" . ?subject rdfs:label ?subjectLabel . }",
    #     "template_id": "T6_PropertyLookup_Inverse"
    # },
    # {
    #     "question": "What is the highest selling The Witcher 3 steel weapon?",
    #     "ground_truth_sparql": "SELECT ?featureLabel ?value WHERE { ?feature a <http://cgi.di.uoa.gr/witcher/ontology#The_Witcher_3_steel_weapons> ; rdfs:label ?featureLabel ; <http://cgi.di.uoa.gr/witcher/ontology#sell> ?value . } ORDER BY DESC(?value) LIMIT 1",
    #     "template_id": "T11_SuperlativeByAttribute"
    # },
    # {
    #     "question": "What kind of thing is a Hydragenum?",
    #     "ground_truth_sparql": "SELECT ?parentClassLabel WHERE { <http://cgi.di.uoa.gr/witcher/ontology#Hydragenum> rdfs:subClassOf ?parentClass . FILTER(isIRI(?parentClass)) ?parentClass rdfs:label ?parentClassLabel . }",
    #     "template_id": "T12_SchemaLookup"
    # }
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
        
        # Get answer keys for BOTH queries
        gt_answer_keys = extract_answer_keys(ground_truth_sparql)
        gen_answer_keys = extract_answer_keys(generated_sparql)

        ground_truth_results = execute_and_get_results(ground_truth_sparql, is_superlative)
        generated_results = execute_and_get_results(generated_sparql, is_superlative)

        # EA is still a strict comparison of the full rows
        is_correct_ea = (
            "error" not in generated_results and "error" not in ground_truth_results and
            generated_results.get("rows") == ground_truth_results.get("rows")
        )
        
        # F1 is now the robust, value-based comparison
        f1 = 0.0
        if "boolean" in ground_truth_results:
            f1 = 1.0 if generated_results.get("boolean") == ground_truth_results.get("boolean") else 0.0
        else:
            f1 = calculate_f1_score(
                generated_results.get("bindings", []),
                ground_truth_results.get("bindings", []),
                gen_answer_keys,
                gt_answer_keys
            )

        # --- Print Final Report ---
        print("\n" + "-"*20, "Evaluation Report", "-"*20)
        print("\n--- Ground-Truth SPARQL ---")
        print(ground_truth_sparql)
        print("\n--- Generated SPARQL ---")
        print(generated_sparql)
        print("\n--- METRICS ---")
        print(f"  - Execution Accuracy: {'CORRECT' if is_correct_ea else 'INCORRECT'}")
        print(f"  - F1-Score: {f1:.4f}")
        print("-" * 50)

if __name__ == "__main__":
    main()