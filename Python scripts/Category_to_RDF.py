import xml.etree.ElementTree as ET
import re
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL

# --- Configuration ---
ONTOLOGY_PREFIX = "witcher"
BASE_URI = f"http://cgi.di.uoa.gr/{ONTOLOGY_PREFIX}/ontology#"

# Initialize the graph and bind namespaces
g = Graph()
witcher = Namespace(BASE_URI)
dbr = Namespace(f"http://cgi.di.uoa.gr/{ONTOLOGY_PREFIX}/resource/") # Resource namespace
g.bind("witcher", witcher)
g.bind("dbr", dbr)
g.bind("owl", OWL)
g.bind("rdfs", RDFS)

# --- Helper Functions ---
def sanitize_for_uri(title):
    """Replaces all non-alphanumeric characters with underscores."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', title)

def extract_full_text(element):
    """Extracts text from an element, including from its children's tails."""
    if element is None: return ""
    return "".join(element.itertext())

# --- 1. Generate Class Hierarchy from Wiki Categories ---
print("Parsing wiki categories to build class hierarchy...")
try:
    tree = ET.parse('../Wiki_Dump_Namespaces/namespace_14_Category.xml')
    root = tree.getroot()

    for page in root.findall('page'):
        title_text = page.find('title').text.replace("Category:", "")
        class_uri = witcher[sanitize_for_uri(title_text)]
        
        # Declare the class
        g.add((class_uri, RDF.type, OWL.Class))
        g.add((class_uri, RDFS.label, Literal(title_text.replace("_", " "))))
        
        # Find and add parent class relationships
        text = extract_full_text(page.find('text'))
        parent_matches = re.findall(r'\[\[Category:([^\]]+)\]\]', text)
        for parent_title in parent_matches:
            parent_uri = witcher[sanitize_for_uri(parent_title)]
            g.add((class_uri, RDFS.subClassOf, parent_uri))
    print("Successfully generated class hierarchy from categories.")

except FileNotFoundError:
    print("Warning: Category XML file not found. No class hierarchy will be built.")

# --- 2. Manually Define Mappin Ontology and Relationships ---
print("Adding specific axioms for map pins and game concepts...")

# Define a top-level class for all map pins
mappin_base_class = witcher.Mappin
g.add((mappin_base_class, RDF.type, OWL.Class))
g.add((mappin_base_class, RDFS.label, Literal("Map Pin")))

# Define functional sub-categories of map pins
crafting_station = witcher.Crafting_Station
g.add((crafting_station, RDFS.subClassOf, mappin_base_class))
g.add((crafting_station, RDFS.label, Literal("Crafting Station")))

road_sign = witcher.RoadSign
g.add((road_sign, RDFS.subClassOf, mappin_base_class))
g.add((road_sign, RDFS.label, Literal("Road Sign")))

# Define specific mappin types as subclasses
g.add((witcher.Blacksmith, RDFS.subClassOf, crafting_station))
g.add((witcher.Armorer, RDFS.subClassOf, crafting_station))
g.add((witcher.Whetstone, RDFS.subClassOf, crafting_station))
g.add((witcher.AlchemyTable, RDFS.subClassOf, crafting_station))
g.add((witcher.AlchemyTable, RDFS.subClassOf, crafting_station))
g.add((witcher.Grindstone, RDFS.subClassOf, witcher.Whetstone)) # A Grindstone is a type of Whetstone

# Link game concepts (professions) to the mappin types they use
# This creates the crucial connection between the person and the map icon.
uses_mappin_type = witcher.usesMappinType
g.add((uses_mappin_type, RDF.type, OWL.ObjectProperty))
g.add((uses_mappin_type, RDFS.label, Literal("uses mappin type")))

# The Blacksmith profession uses the Blacksmith mappin type
g.add((dbr.Blacksmith, uses_mappin_type, witcher.Blacksmith))
g.add((dbr.Armorer, uses_mappin_type, witcher.Armorer))

print("Ontology augmentation complete.")

# --- 3. Save the Combined Ontology ---
with open('../RDF/Classes.ttl', 'w', encoding='utf-8') as f:
    f.write(g.serialize(format='turtle'))

print(f"\nSuccessfully generated enriched ontology file at '../RDF/Classes.ttl'")