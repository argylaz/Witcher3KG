from rdflib import Graph, URIRef, Namespace, RDF, RDFS

# Define Namespaces
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
WITCHER = Namespace("http://example.org/witcher/")

def get_stats(g):
    """Calculates basic KG statistics"""
    triples = len(g)
    subjects = len(set(g.subjects()))
    predicates = len(set(g.predicates()))
    # Classes are usually objects of rdf:type
    classes = len(set(g.objects(None, RDF.type)))
    return triples, subjects, predicates, classes

# 1. Load original Witcher3KG from thesis
print("Loading Witcher3KG...")
g = Graph()
g.parse("../RDF/Witcher3KG.n3", format="n3")

t_init, s_init, p_init, c_init = get_stats(g)
print(f"\n--- Initial Statistics ---")
print(f"Total Triples:  {t_init:,}")
print(f"Total Subjects: {s_init:,}")
print(f"Total Predicates: {p_init:,}")
print(f"Total Classes:  {c_init:,}")

# 2. Identify Geospatial Entities to remove
# We target anything that is a geo:Geometry
print("\nIdentifying geospatial entities...")
geometries = list(g.subjects(RDF.type, GEO.Geometry))

# 3. Cleaning Process
print(f"Removing {len(geometries):,} Geometry entities and associated edges...")

for geo in geometries:
    g.remove((geo, None, None)) # Remove outgoing edges from the geometry
    g.remove((None, None, geo)) # Remove incoming edges pointing to the geometry

# 4. Remove specific geospatial properties that might be attached to lore nodes
# Such as witcher:hasInGameCoordinates or geo:hasGeometry
print("Pruning geospatial predicates...")
g.remove((None, GEO.hasGeometry, None))
g.remove((None, GEO.asWKT, None))
# Add your specific thesis property here if it's named differently:
g.remove((None, WITCHER.hasInGameCoordinates, None))

# 5. Final Statistics
t_final, s_final, p_final, c_final = get_stats(g)
print(f"\n--- Final Relational Statistics ---")
print(f"Total Triples:  {t_final:,} (Dropped {t_init - t_final:,})")
print(f"Total Subjects: {s_final:,}")
print(f"Total Predicates: {p_final:,}")
print(f"Total Classes:  {c_final:,}")

# 6. Save the new subset
g.serialize(destination="../RDF/Witcher3KG_Relational.n3", format="n3")
print("\nCleaned graph saved as: Witcher3KG_Relational.ttl")