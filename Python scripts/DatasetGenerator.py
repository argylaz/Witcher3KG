import json
import random
from itertools import product, combinations
from collections import defaultdict
from SPARQLWrapper import SPARQLWrapper, JSON
import time

# --- 1. CONFIGURATION ---
SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final" # SPARQL ENDPOINT
OUTPUT_FILE = "witcher_benchmark_dataset_final_v7.json"
USER_AGENT = "WitcherKG-Benchmark-Generator/1.0"
POLYGON_SAMPLE_SIZE = 50
POINT_SAMPLE_SIZE = 100
LANDMARK_POI_SAMPLE = 50
GUIDED_GENERATION_LIMIT = 200
COMBINATORIAL_TEMPLATE_LIMIT = 500

# --- HELPER FUNCTIONS ---
def execute_sparql_query(query):
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.agent = USER_AGENT
    try:
        results = sparql.query().convert()
        return results["results"]["bindings"]
    except Exception as e:
        print(f"\nSPARQL query failed. Error: {e}")
        return None

def format_sparql_term(term_dict):
    if not term_dict: return '""' # Handle cases where object might be missing
    if term_dict['type'] == 'uri':
        return f"<{term_dict['value']}>"
    else:
        literal = term_dict['value'].replace('"', '\\"').replace('\n', '\\n')
        formatted_term = f'"{literal}"'
        if 'xml:lang' in term_dict:
            formatted_term += f"@{term_dict['xml:lang']}"
        elif 'datatype' in term_dict:
            formatted_term += f"^^<{term_dict['datatype']}>"
        return formatted_term

# --- 2. SEEDING STAGE (DYNAMIC AND DATA-DRIVEN) ---
print("Starting Data-Driven Seeding Stage...")
namespaces = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX geo: <http://www.opengis.net/ont/geosparql#>
    PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

def get_uris(query):
    results = execute_sparql_query(f"{namespaces} {query}")
    return [r['s']['value'] for r in results] if results else []

# --- Basic Entity & Geometry Lists ---
locations_with_polygons = get_uris("SELECT DISTINCT ?s WHERE { ?s geo:hasGeometry/geo:asWKT ?wkt . FILTER(STRSTARTS(STR(?wkt), 'POLYGON') || STRSTARTS(STR(?wkt), 'MULTIPOLYGON')) }")
locations_with_points = get_uris("SELECT DISTINCT ?s WHERE { ?s geo:hasGeometry/geo:asWKT ?wkt . FILTER(STRSTARTS(STR(?wkt), 'POINT')) }")
cities = get_uris("SELECT ?s WHERE { ?s a witcher:City . }")
quests = get_uris("SELECT ?s WHERE { ?s a witcher:The_Witcher_3_quests . }")
characters = get_uris("SELECT ?s WHERE { ?s a witcher:The_Witcher_3_characters . }")
poi_types = get_uris("SELECT ?s WHERE { ?s rdfs:subClassOf witcher:Mappin . }")
all_classes = get_uris("SELECT DISTINCT ?s WHERE { [] a ?s . FILTER(STRSTARTS(STR(?s), STR(witcher:))) }")
landmark_locations = list(set(cities + random.sample(locations_with_points, min(len(locations_with_points), LANDMARK_POI_SAMPLE))))
geospatial_functions = ["sfWithin", "sfIntersects", "sfTouches"]
order_directions = ["ASC", "DESC"]

# --- Advanced Guided Generation Seeders ---
print("Fetching guaranteed-valid combinations for complex templates...")

# T1: Find (POI Type, Polygon) pairs that are guaranteed to have a match
valid_spatial_relations_res = execute_sparql_query(f"""{namespaces}
    SELECT DISTINCT ?poi_type ?poly_loc WHERE {{
        ?poly_loc geo:hasGeometry/geo:asWKT ?poly_wkt .
        FILTER(STRSTARTS(STR(?poly_wkt), "POLYGON") || STRSTARTS(STR(?poly_wkt), "MULTIPOLYGON"))
        ?poi a ?poi_type ; geo:hasGeometry/geo:asWKT ?point_wkt .
        FILTER(geof:sfWithin(?point_wkt, ?poly_wkt))
    }} LIMIT {GUIDED_GENERATION_LIMIT}
""")
valid_spatial_relations = [(r['poi_type']['value'], r['poly_loc']['value']) for r in valid_spatial_relations_res] if valid_spatial_relations_res else []

# T3: Find locations that are actually part of a map
valid_map_context_pairs_res = execute_sparql_query(f"{namespaces} SELECT DISTINCT ?loc ?map WHERE {{ ?loc witcher:isPartOf ?map . ?map a witcher:Maps . }} LIMIT {GUIDED_GENERATION_LIMIT}")
valid_map_context_pairs = [(r['loc']['value'], r['map']['value']) for r in valid_map_context_pairs_res] if valid_map_context_pairs_res else []

# T5/T6: Dynamically find properties for a sample of entities
entities_for_props = random.sample(characters + quests + landmark_locations, min(len(characters + quests + landmark_locations), 100))
values_clause = "VALUES ?s { " + " ".join([f"<{uri}>" for uri in entities_for_props]) + " }"
valid_property_triples_res = execute_sparql_query(f"{namespaces} SELECT ?s ?p ?o WHERE {{ {values_clause} ?s ?p ?o . FILTER(STRSTARTS(STR(?p), STR(witcher:))) }} LIMIT {GUIDED_GENERATION_LIMIT}")
valid_property_triples = [(r['s']['value'], r['p']['value'], r['o']) for r in valid_property_triples_res] if valid_property_triples_res else []


# T7: Dynamic Multi-Hop Path Discovery
print("  - Discovering valid multi-hop paths for T7...")
valid_multihop_quads = []
# Find relationships to use as the "first hop"
first_hop_candidates = [t for t in valid_property_triples if t[2]['type'] == 'uri']
for subject, prop1, obj in random.sample(first_hop_candidates, min(len(first_hop_candidates), 20)):
    # Now find a "second hop" from the subject
    second_hop_res = execute_sparql_query(f"{namespaces} SELECT ?p2 WHERE {{ <{subject}> ?p2 ?o2 . FILTER(?p2 != <{prop1}> && STRSTARTS(STR(?p2), STR(witcher:))) }}")
    if second_hop_res:
        for res in second_hop_res:
            prop2 = res['p2']['value']
            # The query starts with the object of the first hop
            valid_multihop_quads.append((obj['value'], prop1, prop2))
            if len(valid_multihop_quads) >= GUIDED_GENERATION_LIMIT: break
    if len(valid_multihop_quads) >= GUIDED_GENERATION_LIMIT: break


# T8: Robust seeder
sampled_polygons_str = " ".join([f"<{uri}>" for uri in random.sample(locations_with_polygons, min(len(locations_with_polygons), 10))])
valid_composed_quads_res = execute_sparql_query(f"""{namespaces}
    SELECT ?loc ?entityType ?p ?o WHERE {{
        VALUES ?loc {{ {sampled_polygons_str} }}
        ?loc geo:hasGeometry/geo:asWKT ?poly .
        ?entity a ?entityType ; geo:hasGeometry/geo:asWKT ?point ; ?p ?o .
        FILTER(geof:sfWithin(?point, ?poly))
        FILTER(STRSTARTS(STR(?p), STR(witcher:)))
    }} LIMIT {GUIDED_GENERATION_LIMIT}
""")
valid_composed_quads = [(r['loc']['value'], r['entityType']['value'], r['p']['value'], r['o']) for r in valid_composed_quads_res] if valid_composed_quads_res else []

# T11: Robust seeder using REGEX
valid_superlative_pairs_res = execute_sparql_query(f"""{namespaces}
    SELECT DISTINCT ?class ?p WHERE {{
        ?s a ?class ; ?p ?o .
        FILTER(REGEX(STR(?o), "^-?[0-9]+(\\\\.?[0-9]+)?$"))
        FILTER(STRSTARTS(STR(?class), STR(witcher:)))
    }} LIMIT {GUIDED_GENERATION_LIMIT}
""")
valid_superlative_pairs = [(r['class']['value'], r['p']['value']) for r in valid_superlative_pairs_res] if valid_superlative_pairs_res else []

# T13: Robust, optimized seeder
city_pois_res = execute_sparql_query(f"""{namespaces} SELECT DISTINCT ?city ?poi_type WHERE {{ ?city a witcher:City ; geo:hasGeometry/geo:asWKT ?poly . ?poi a ?poi_type ; geo:hasGeometry/geo:asWKT ?point . FILTER(geof:sfWithin(?point, ?poly)) }}""")
city_to_poi_types = defaultdict(set)
if city_pois_res:
    for res in city_pois_res: city_to_poi_types[res['city']['value']].add(res['poi_type']['value'])
valid_combo_locations = []
for city, types in city_to_poi_types.items():
    if len(types) >= 2:
        for combo in combinations(list(types), 2):
            valid_combo_locations.append((city, combo[0], combo[1]))
            if len(valid_combo_locations) >= GUIDED_GENERATION_LIMIT: break
    if len(valid_combo_locations) >= GUIDED_GENERATION_LIMIT: break

print("Seeding complete.")
print(f"  - T3: Found {len(valid_map_context_pairs)} valid map contexts.")
print(f"  - T5/T6: Found {len(valid_property_triples)} valid properties for entities.")
print(f"  - T8: Found {len(valid_composed_quads)} valid composed query combinations.")
print(f"  - T11: Found {len(valid_superlative_pairs)} properties with numeric values.")
print(f"  - T13: Found {len(valid_combo_locations)} cities with multiple POI types.")


# --- 3. TEMPLATE DEFINITIONS (Updated to use new guided lists) ---
templates = [
    {
        "id": "T3_LocationContextDiscovery", "type": "SELECT", "inputs": valid_map_context_pairs,
        "template": """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#> SELECT ?mapLabel WHERE {{ <{0}> witcher:isPartOf <{1}> . <{1}> rdfs:label ?mapLabel . }}"""
    },
    {
        "id": "T5_PropertyLookup_Direct", "type": "SELECT", "inputs": valid_property_triples,
        "template": """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?objectLabel WHERE {{ <{0}> <{1}> ?object . OPTIONAL {{ ?object rdfs:label ?objLabel . }} BIND(IF(isURI(?object), ?objLabel, ?object) AS ?objectLabel) }}"""
    },
    {
        "id": "T6_PropertyLookup_Inverse", "type": "SELECT", "inputs": valid_property_triples,
        "template": """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?subjectLabel WHERE {{ ?subject <{1}> {2} . ?subject rdfs:label ?subjectLabel . }}"""
    },
    {
        "id": "T8_ComposedQuery", "type": "SELECT", "inputs": valid_composed_quads,
        "template": """PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX geof: <http://www.opengis.net/def/function/geosparql/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?entityLabel WHERE {{ <{0}> geo:hasGeometry/geo:asWKT ?polygonWKT . ?entity a <{1}> ; <{2}> {3} ; rdfs:label ?entityLabel ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }}"""
    },
    {
        "id": "T11_SuperlativeByAttribute", "type": "SELECT", "inputs": [(pair[0], pair[1], direction) for pair in valid_superlative_pairs for direction in order_directions],
        "template": """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?featureLabel ?value WHERE {{ ?feature a <{0}> ; rdfs:label ?featureLabel ; <{1}> ?value . }} ORDER BY {2}(?value) LIMIT 1"""
    },
    {
        "id": "T13_FindLocationByFeatureCombination", "type": "SELECT", "inputs": [cities, poi_types, poi_types],#valid_combo_locations,
        "template": """PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX geof: <http://www.opengis.net/def/function/geosparql/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT DISTINCT ?locationLabel WHERE {{ <{0}> rdfs:label ?locationLabel ; geo:hasGeometry/geo:asWKT ?polygonWKT . FILTER ( EXISTS {{ ?featureA a <{1}> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polygonWKT)) }} || EXISTS {{ ?featureB a <{2}> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polygonWKT)) }} ) }}"""
    },
    ###################################################
    {
        "id": "T1_SpatialRelationship", "type": "SELECT", "inputs": [poi_types, cities],#valid_spatial_relations,
        "template": """PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX geof: <http://www.opengis.net/def/function/geosparql/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?featureA ?featureALabel WHERE {{ <{1}> geo:hasGeometry/geo:asWKT ?geomB_WKT . ?featureA a <{0}> ; rdfs:label ?featureALabel ; geo:hasGeometry/geo:asWKT ?geomA_WKT . FILTER(geof:sfWithin(?geomA_WKT, ?geomB_WKT)) }} LIMIT 10"""
    },
    {
        "id": "T2_ProximitySearch", "type": "SELECT", "inputs": [poi_types, landmark_locations, order_directions],
        "template": """PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX geof: <http://www.opengis.net/def/function/geosparql/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?featureALabel (geof:distance(?wktA, ?wktB) AS ?distance) WHERE {{ <{1}> geo:hasGeometry/geo:asWKT ?wktB . ?featureA a <{0}> ; rdfs:label ?featureALabel ; geo:hasGeometry/geo:asWKT ?wktA . }} ORDER BY {2}(?distance) LIMIT 1"""
    },
    {
        "id": "T4_GeospatialVerification", "type": "ASK", "inputs": [random.sample(locations_with_points, min(len(locations_with_points), POINT_SAMPLE_SIZE)), ["sfWithin"], random.sample(locations_with_polygons, min(len(locations_with_polygons), POLYGON_SAMPLE_SIZE))],
        "template": """PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX geof: <http://www.opengis.net/def/function/geosparql/> ASK WHERE {{ <{0}> geo:hasGeometry/geo:asWKT ?geomA_WKT . <{2}> geo:hasGeometry/geo:asWKT ?geomB_WKT . FILTER(geof:{1}(?geomA_WKT, ?geomB_WKT)) }}"""
    },
    {
        "id": "T7_MultiHopQuery", "type": "SELECT", "inputs": valid_multihop_quads,
        # A fully generic multi-hop template
        "template": """
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?targetValueLabel WHERE {{
                ?member <{1}> <{0}> .
                ?member <{2}> ?targetValue .
                OPTIONAL {{ ?targetValue rdfs:label ?label . }}
                BIND(IF(isURI(?targetValue), ?label, ?targetValue) AS ?targetValueLabel)
            }}
        """
    },
    {
        "id": "T9_SpatialCounting", "type": "SELECT", "inputs": [random.sample(locations_with_polygons, min(len(locations_with_polygons), POLYGON_SAMPLE_SIZE)), poi_types],
        "template": """PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX geof: <http://www.opengis.net/def/function/geosparql/> SELECT (COUNT(?feature) as ?count) WHERE {{ <{0}> geo:hasGeometry/geo:asWKT ?polygonWKT . ?feature a <{1}> ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }}"""
    },
    {
        "id": "T10_ComparativeCounting", "type": "SELECT", "inputs": [random.sample(locations_with_polygons, min(len(locations_with_polygons), POLYGON_SAMPLE_SIZE)), poi_types, random.sample(locations_with_polygons, min(len(locations_with_polygons), POLYGON_SAMPLE_SIZE))],
        "template": """PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX geof: <http://www.opengis.net/def/function/geosparql/> SELECT (IF(?countA > ?countB, "Yes", "No") AS ?result) WHERE {{ {{ SELECT (COUNT(?featureA) as ?countA) WHERE {{ <{0}> geo:hasGeometry/geo:asWKT ?polyA . ?featureA a <{1}> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polyA)) }} }} {{ SELECT (COUNT(?featureB) as ?countB) WHERE {{ <{2}> geo:hasGeometry/geo:asWKT ?polyB . ?featureB a <{1}> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polyB)) }} }} }}"""
    },
    {
        "id": "T12_SchemaLookup", "type": "SELECT", "inputs": [all_classes],
        "template": """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?parentClassLabel WHERE {{ <{0}> rdfs:subClassOf ?parentClass . FILTER(isIRI(?parentClass)) ?parentClass rdfs:label ?parentClassLabel . }}"""
    },
    {
        "id": "T14_InstanceListingByClass", "type": "SELECT", "inputs": [all_classes],
        "template": """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?instanceLabel WHERE {{ ?instance a <{0}> . ?instance rdfs:label ?instanceLabel . }}"""
    },
    {
        "id": "T15_PathVerification", "type": "ASK", "inputs": [landmark_locations, landmark_locations],
        "template": """PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX geof: <http://www.opengis.net/def/function/geosparql/> PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#> ASK WHERE {{ <{0}> geo:hasGeometry/geo:asWKT ?geomA. <{1}> geo:hasGeometry/geo:asWKT ?geomB. ?path a witcher:Road ; geo:hasGeometry/geo:asWKT ?pathGeom . FILTER(geof:sfIntersects(?pathGeom, ?geomA) && geof:sfIntersects(?pathGeom, ?geomB)) }}"""
    }
]


# --- 4. GENERATION AND VALIDATION STAGE (Fortified Loop) ---
print("\nStarting Generation and Validation Stage...")
valid_queries = []
query_counter = 0

guided_templates = [
    "T3_LocationContextDiscovery", "T5_PropertyLookup_Direct", "T6_PropertyLookup_Inverse",
    "T7_MultiHopQuery",
    "T8_ComposedQuery", "T11_SuperlativeByAttribute"
]
high_volume_templates = [
    'T1_SpatialRelationship', 'T2_ProximitySearch', 'T4_GeospatialVerification',
    'T9_SpatialCounting', 'T10_ComparativeCounting',
    'T12_SchemaLookup', 'T13_FindLocationByFeatureCombination',
    'T14_InstanceListingByClass', 'T15_PathVerification'
]

for t in templates:
    template_id, query_type, template_str, inputs = t['id'], t['type'], t['template'], t['inputs']
    is_guided = template_id in guided_templates

    if is_guided and not inputs:
        print(f"\nProcessing template: {template_id} (Strategy: Guided) - SKIPPING (no valid combinations found)")
        continue

    if is_guided:
        input_combinations = inputs
    else:
        shuffled_inputs = [random.sample(inp, len(inp)) if isinstance(inp, list) and len(inp) > 0 else inp for inp in inputs]
        input_combinations = product(*shuffled_inputs)
    
    print(f"\nProcessing template: {template_id} (Strategy: {'Guided' if is_guided else 'Combinatorial'})")
    if template_id in high_volume_templates:
        print(f"  - Applying limit of {COMBINATORIAL_TEMPLATE_LIMIT} valid queries.")

    template_valid_query_count = 0

    for i, combo in enumerate(input_combinations):
        if not isinstance(combo, tuple): combo = (combo,)
        # Self-comparison checks
        if template_id == 'T15_PathVerification' and combo[0] == combo[1]: continue
        if template_id == 'T10_ComparativeCounting' and combo[0] == combo[2]: continue
        if template_id == 'T13_FindLocationByFeatureCombination' and len(combo) > 2 and combo[1] == combo[2]: continue
        
        try:
            query_args = list(combo)
            if template_id == 'T6_PropertyLookup_Inverse':
                query_args[2] = format_sparql_term(combo[2])
            if template_id == 'T8_ComposedQuery':
                query_args[3] = format_sparql_term(combo[3])
            
            query = template_str.format(*query_args)
        except (IndexError, KeyError) as e:
            print(f"  - Skipping combo due to formatting error: {e} | Combo: {combo}")
            continue

        validation_query = query.replace("ASK WHERE", "SELECT * WHERE", 1) + " LIMIT 1" if query_type == "ASK" else query
        results = execute_sparql_query(validation_query)
        time.sleep(0.01)

        if results and len(results) > 0:
            query_counter += 1
            template_valid_query_count += 1
            print(f"  > Found valid query #{query_counter} (template count: {template_valid_query_count})", end='\r')
            valid_queries.append({
                "query_id": f"{template_id}_{i}", "template_id": template_id,
                "query_type": query_type, "query": " ".join(query.strip().split())
            })

            if template_id in high_volume_templates and template_valid_query_count >= COMBINATORIAL_TEMPLATE_LIMIT:
                print(f"\n  > Reached limit of {COMBINATORIAL_TEMPLATE_LIMIT} for {template_id}. Moving to next template.")
                break
    print()

# --- 5. OUTPUT STAGE ---
print(f"\nGeneration complete. Found {len(valid_queries)} total valid queries.")
with open(OUTPUT_FILE, 'w') as f:
    json.dump(valid_queries, f, indent=2)
print(f"Benchmark dataset saved to {OUTPUT_FILE}")