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
infobox_pattern = re.compile(r"\{\{Infobox (.*?)\}\}", re.DOTALL)
infobox_property_pattern = re.compile(r"\|(.*?)=(.*)")

# **Processing file as plain text**
with open('../Wiki_Dump_Namespaces/namespace_0_main.xml', 'r', encoding='utf-8') as file:
    current_title = None  # Store title for pages
    page_text = ""  # Store text content of the page
    
    for line in file:
        # Check for title
        title_match = title_pattern.search(line)
        if title_match:
            categories = category_pattern.findall(page_text)
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

            # Process the previous page before moving to the next
            infobox_match = infobox_pattern.search(page_text)
            if infobox_match:
                subject = dbr[re.sub(r'\W+', '_', current_title).strip('_')]
                for prop_match in infobox_property_pattern.findall(infobox_match.group(1)):
                    prop_name = prop_match[0].strip()
                    prop_value = prop_match[1].strip()
                    prop_uri = witcher[re.sub(r"[^a-zA-Z0-9_-]", "", prop_name.replace(' ', '_'))]
                    g.add((subject, prop_uri, Literal(prop_value)))
                    print(f"Added property: {current_title} -> {prop_name} = {prop_value}")
                
            current_title = title_match.group(1).strip()
            page_text = ""  # Reset text storage for new page
            continue  # Move to the next line

        # Accumulate text for the current page
        if current_title:
            page_text += line

    # Process the last page in the file
    if current_title:
        categories = category_pattern.findall(page_text)
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
        infobox_match = infobox_pattern.search(page_text)
        if infobox_match:
            subject = dbr[re.sub(r'\W+', '_', current_title).strip('_')]
            for prop_match in infobox_property_pattern.findall(infobox_match.group(1)):
                prop_name = prop_match[0].strip()
                prop_value = prop_match[1].strip()
                prop_uri = witcher[re.sub(r"[^a-zA-Z0-9_-]", "", prop_name.replace(' ', '_'))]
                g.add((subject, prop_uri, Literal(prop_value)))
                print(f"Added property: {current_title} -> {prop_name} = {prop_value}")

# **Save RDF Output**
g.serialize('../RDF/main.n3', format='n3')
print(f"Generated {len(g)} triples")
