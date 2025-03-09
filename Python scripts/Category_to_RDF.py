import xml.etree.ElementTree as ET
import re

# Define the ontology prefix
ontology_prefix = "witcher"
base_uri = f"http://cgi.di.uoa.gr/{ontology_prefix}/ontology#"

# Parse the XML file
tree = ET.parse('../Wiki_Dump_Namespaces/namespace_14_Category.xml')
root = tree.getroot()

# Function to sanitize category titles (replace all invalid characters with underscores)
def sanitize_category_title(category_title):
    # Replace all non-alphanumeric characters (except underscores) with underscores
    sanitized_title = re.sub(r'[^a-zA-Z0-9_]', '_', category_title)
    return sanitized_title

# Function to generate RDF class name with prefix
def get_class_name(category_title):
    sanitized_title = sanitize_category_title(category_title.replace("Category:", ""))
    return f"witcher:{sanitized_title}"

# Function to generate RDF triples with prefixes
def generate_rdf_triples(category_title, parent_category=None):
    class_name = get_class_name(category_title)
    triples = [f"{class_name} a owl:Class ."]
    
    if parent_category:
        parent_class_name = get_class_name(parent_category)
        triples.append(f"{class_name} rdfs:subClassOf {parent_class_name} .")
    
    return triples

# Function to extract full text content, including text after child elements
def extract_full_text(element):
    if element is None:
        return ""
    
    # Start with the .text of the element
    full_text = element.text or ""
    
    # Iterate through child elements and add their .tail
    for child in element:
        if child.tail:
            full_text += child.tail
    
    return full_text

# Iterate through each category and generate RDF triples
rdf_triples = []
for page in root.findall('page'):
    title = page.find('title').text
    text_element = page.find('text')
    
    # Extract full text content, including text after child elements
    text = extract_full_text(text_element)
    
    # Extract parent category if any
    parent_category = None
    if "[[Category:" in text:
        parent_category = text.split("[[Category:")[1].split("]]")[0]
    
    # Generate RDF triples
    triples = generate_rdf_triples(title, parent_category)
    rdf_triples.extend(triples)

# Write the RDF triples to a file in Turtle format
with open('../RDF/Classes.ttl', 'w', encoding='utf-8') as f:
    f.write("@prefix witcher: <{}> .\n".format(base_uri))
    f.write("@prefix owl: <http://www.w3.org/2002/07/owl#> .\n")
    f.write("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n")
    f.write("\n".join(rdf_triples))