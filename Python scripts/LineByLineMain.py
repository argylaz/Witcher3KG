import re
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL

# Initialize RDF Graph
g = Graph()
witcher = Namespace("http://cgi.di.uoa.gr/witcher/ontology#")
dbr = Namespace("http://cgi.di.uoa.gr/witcher/resource/")

g.bind("witcher", witcher)
g.bind("dbr", dbr)
g.bind("owl", OWL)

# Load ontology to get existing OWL classes
g.parse('../RDF/Classes.ttl', format='turtle')
existing_classes = set()
for s in g.subjects(RDF.type, OWL.Class):
    if isinstance(s, URIRef) and s.startswith(str(witcher)):
        class_name = s.split('#')[-1].replace('_', ' ')
        existing_classes.add(class_name.lower())

print("Loaded OWL Classes:", existing_classes)

# **Regex patterns for extraction**
title_pattern = re.compile(r"<title>(.*?)</title>")
category_pattern = re.compile(r"\[\[Category:(.*?)\]\]")

# **Processing file as plain text**
with open('../Wiki_Dump_Namespaces/namespace_0_main.xml', 'r', encoding='utf-8') as file:
    current_title = None  # Store title for pages
    for line in file:
        # Check for title
        title_match = title_pattern.search(line)
        if title_match:
            current_title = title_match.group(1).strip()
            continue  # Move to the next line

        # If inside a page and found category
        if current_title:
            categories = category_pattern.findall(line)
            for cat in categories:
                cat_name = cat.split('|')[0].strip().replace('_', ' ')
                if cat_name.lower() in existing_classes:
                    subject = dbr[re.sub(r'\W+', '_', current_title).strip('_')]

                    # Clean category name for URI
                    cleaned_cat = re.sub(r"[^a-zA-Z0-9_-]", "", cat.replace(' ', '_'))  
                    class_uri = witcher[cleaned_cat]

                    g.add((subject, RDF.type, class_uri))
                    g.add((subject, RDFS.label, Literal(current_title)))
                    print(f"Added instance: {current_title} -> {cat}")

# **Save RDF Output**
g.serialize('../RDF/main.n3', format='n3')
print(f"Generated {len(g)} triples")

