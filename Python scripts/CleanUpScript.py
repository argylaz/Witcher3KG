import re
from rdflib import Graph, Namespace, URIRef, Literal, RDFS

# ——————————————————————————————
# Configuration
# ——————————————————————————————
DBR     = Namespace("http://cgi.di.uoa.gr/witcher/resource/")
WITCHER = Namespace("http://cgi.di.uoa.gr/witcher/ontology#")

# Input & output N3 paths
INPUT_N3  = "../RDF/main.n3"    # your N3 with literals like "[[Foo]]" or "[[Bar|Baz]]"
OUTPUT_N3 = "../RDF/main.n3"  # N3 to write with URIRefs in place of those literals

# Regex for a single wiki-link literal
WIKILINK = re.compile(r'^\[\[([^|\]]+)(?:\|([^\]]+))?\]\]$')

# ——————————————————————————————
# Processing function
# ——————————————————————————————
def resolve_wikilinks_n3(input_path: str, output_path: str):
    g = Graph()
    # Parse N3 format
    g.parse(input_path, format="n3")
    # Bind namespaces for cleaner output
    g.bind("dbr", DBR)
    g.bind("witcher", WITCHER)
    g.bind("rdfs", RDFS)

    to_remove = []
    to_add    = []

    # Iterate over triples
    for subj, pred, obj in g:
        if isinstance(obj, Literal):
            text = str(obj).strip()
            m = WIKILINK.match(text)
            if m:
                # Schedule removal of the old literal triple
                to_remove.append((subj, pred, obj))

                # Extract page and optional label
                page, label = m.groups()
                uri = DBR[ re.sub(r'\W+', '_', page).strip('_') ]

                # Add the new link triple
                to_add.append((subj, pred, uri))
                # Add label triple if custom label provided
                if label:
                    to_add.append((uri, RDFS.label, Literal(label)))

    # Apply removals and additions
    for triple in to_remove:
        g.remove(triple)
    for triple in to_add:
        g.add(triple)

    # Serialize back to N3
    g.serialize(destination=output_path, format="n3")
    print(f"Replaced {len(to_remove)} link-literals; graph now has {len(g)} triples.")
    print(f"Cleaned N3 written to: {output_path}")

if __name__ == "__main__":
    resolve_wikilinks_n3(INPUT_N3, OUTPUT_N3)
