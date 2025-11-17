### S

from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, Literal, BNode
import re
import os

# --- Configuration ---
# The single, primary knowledge graph file to read from AND write to.
FINAL_GRAPH_PATH = '../../RDF/Witcher3KG.n3' 
# The namespace of the properties
WITCHER_NS = "http://cgi.di.uoa.gr/witcher/ontology#"

def enrich_graph_with_property_definitions(graph_path, namespace):
    """
    Loads a knowledge graph, discovers all used properties in a given namespace,
    adds the formal OWL definitions for them directly back into the graph,
    and saves the enriched graph back to the same file.
    """
    # --- Step 1: Load the entire knowledge graph ---
    g = Graph()
    # Ensure the directory exists before trying to read from it
    if not os.path.exists(graph_path):
        print(f"!!! FATAL ERROR: Knowledge graph file not found at {graph_path} !!!")
        return

    print(f"Loading knowledge graph from {graph_path}...")
    g.parse(graph_path, format='n3')
    print("Graph loaded successfully.")

    # Bind namespaces for clean output
    witcher = Namespace(namespace)
    g.bind("witcher", witcher)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)

    # --- Step 2: Discover all properties in the graph that need defining ---
    query = f"""
        SELECT DISTINCT ?p (SAMPLE(?o) AS ?sampleObject)
        WHERE {{
            ?s ?p ?o .
            FILTER(STRSTARTS(STR(?p), "{namespace}"))
        }}
        GROUP BY ?p
    """
    results = g.query(query)
    print(f"Discovered {len(results)} unique properties in the '{namespace}' namespace to define.")

    # --- Step 3: Add definitions for NEW properties directly to the graph ---
    properties_added = 0
    for row in results:
        prop_uri = row.p
        sample_object = row.sampleObject

        # Check if the property is already defined to avoid duplicates
        if (prop_uri, RDF.type, None) in g:
            # More specific check: is it already an OWL property?
            is_already_defined = False
            for prop_type in g.objects(prop_uri, RDF.type):
                if prop_type in [OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty]:
                    is_already_defined = True
                    break
            if is_already_defined:
                continue

        def create_label_from_uri(uri):
            local_name = str(uri).split('#')[-1]
            s1 = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', local_name)
            return re.sub('([a-z0-9])([A-Z])', r'\1 \2', s1).replace('_', ' ').title()

        prop_label = create_label_from_uri(prop_uri)
        
        # Determine and add the property type
        if isinstance(sample_object, (URIRef, BNode)):
            g.add((prop_uri, RDF.type, OWL.ObjectProperty))
        else:
            g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        
        g.add((prop_uri, RDFS.label, Literal(prop_label)))
        properties_added += 1

    print(f"\nAdded definitions for {properties_added} new properties to the graph.")

    # --- Step 4: Save the enriched graph back to the same file ---
    print(f"Saving enriched graph back to {graph_path}...")
    with open(graph_path, 'w', encoding='utf-8') as f:
        # We serialize in 'turtle' format because it's cleaner and a superset of what N3 offers in this context.
        # It will correctly handle all your data.
        f.write(g.serialize(format='turtle'))
        
    print("Successfully enriched and saved the final knowledge graph.")

if __name__ == '__main__':
    enrich_graph_with_property_definitions(FINAL_GRAPH_PATH, WITCHER_NS)